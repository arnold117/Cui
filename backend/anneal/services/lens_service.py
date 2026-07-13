"""Lens service — cross-idea contradiction detection (Lens 第一刀 / L3 tracer).

At grill time, scans the user's OWN Library for already-grilled claims
(``survived`` / ``killed``) that contradict, duplicate, or stand in tension with
the claim being grilled, and surfaces each hit as a PENDING ``CHALLENGE`` event
(``payload.kind="lens_contradiction"``). This is Lens's first "read-out": it
wires "history → current grill" without building any persistent Lens store or
embedding index — everything is computed on the fly.

Two ironclad rules (spec §6):
- 只吃 grilled trajectory，永不吃 PARK — candidates must have a confirmed
  survive/kill verdict; PARK-only / open claims never qualify.
- 取证不定见 — the system surfaces the conflict as a pending challenge and
  NEVER scores idea quality or decides the current claim's fate.

Mirrors GrillService's shape: LLM guard, prompt builder, ``complete_json``,
``make_event(CHALLENGE, actor="system", confirmed=False, ...)``, append via
EventService. Retract is handled for free — ``claim_status`` already folds back
retracted verdicts, so a reverted verdict drops a candidate without any special
casing.

Dependency: EventStore + EventService + Repository -> LensService.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from anneal.domain.events import CHALLENGE, GROUND, LINK, VERDICT, Event, make_event
from anneal.domain.projections import (
    VerdictPrecedent,
    _confirmed_event_ids,
    claim_status,
    ground_stance,
    retracted_event_ids,
    verdict_precedent,
)
from anneal.lens.prefilter import prefilter_candidates
from anneal.llm.client import LLMClient
from anneal.llm.errors import LLMNotConfiguredError
from anneal.llm.prompts import (
    ClaimPrecedent,
    build_contradiction_prompt,
    build_semantic_edges_prompt,
    build_taste_prompt,
)
from anneal.search.openalex import search_openalex
from anneal.services.collect_service import _load_contact_email
from anneal.services.event_service import EventService
from anneal.store.event_store import EventStore
from anneal.store.repository import Repository

# Past-claim outcomes that qualify as grilled trajectory (candidate set).
_GRILLED_STATUSES = {"survived", "killed"}

# The four taste rubric tiers (spec §2). Anything else = no verdict.
_TASTE_TIERS = {"replication", "incremental", "novel_but_tasteless", "tasteful"}

# The four LLM-computed semantic edge types (Tier 1). Anything else = dropped.
# ``contradicts``/``grounds`` are NOT here — they are structural (① + GROUND).
_SEMANTIC_EDGE_TYPES = {"builds_on", "depends_on", "shares_method", "shares_gap"}


# ---------------------------------------------------------------------------
# Corpus graph (Lens 第三刀 / ③ 可查询语料 — Tier 0, pure structural projection)
# ---------------------------------------------------------------------------


class GraphNode(BaseModel):
    """A node in the corpus graph — a claim or a grounded material."""

    id: str
    type: Literal["claim", "material"]
    label: str
    status: str | None = None  # claim_status for claims; None for materials


class GraphEdge(BaseModel):
    """A confirmed relationship between two nodes.

    ``contradicts``/``grounds``/``undermines`` are Tier 0 structural edges
    (``grounds``: supporting evidence, ``claim —grounds→ material``;
    ``undermines``: counter-evidence from a confirmed contradicts GROUND,
    ``material —undermines→ claim`` — deterministic, pure read, zero new
    storage); ``builds_on`` / ``depends_on`` / ``shares_method`` /
    ``shares_gap`` are Tier 1 LLM-computed semantic edges read back from
    confirmed ``LINK`` events; ``narrowed_from`` is a deterministic (non-LLM)
    lineage edge read from boundary-kill verdict payloads
    (``successor —narrowed_from→ killed claim``).
    """

    source: str
    target: str
    type: Literal[
        "contradicts",
        "grounds",
        "undermines",
        "builds_on",
        "depends_on",
        "shares_method",
        "shares_gap",
        "narrowed_from",
    ]


class CorpusGraph(BaseModel):
    """The user's Library corpus as a graph (Tier 0: zero LLM / persistence)."""

    nodes: list[GraphNode]
    edges: list[GraphEdge]


class LensService:
    """Detects contradictions between the current claim and grilled past claims."""

    def __init__(
        self,
        store: EventStore,
        event_service: EventService,
        repo: Repository,
        llm: LLMClient | None = None,
    ) -> None:
        self._store = store
        self._event_service = event_service
        self._repo = repo
        self._llm = llm

    def scan_contradictions(
        self,
        artifact_id: str,
        claim_id: str,
        claim_body: str,
        include_soft: bool = False,
    ) -> list[Event]:
        """Scan the Library for contradictions with the current claim.

        Returns the list of PENDING ``CHALLENGE`` events created (empty if no
        hits). Surfaces hard contradictions + duplicates always; soft tensions
        only when ``include_soft`` is True (default OFF, spec §2 检测档位).

        Raises ``LLMNotConfiguredError`` if no LLM client is injected and
        ``ValueError`` if the current artifact cannot be resolved.
        """
        if self._llm is None:
            raise LLMNotConfiguredError("LLM client not configured")

        artifact = self._repo.get_artifact(artifact_id)
        if artifact is None:
            raise ValueError(f"Artifact {artifact_id!r} not found")
        library_id = artifact.library_id

        candidates = self._grilled_candidates(library_id, claim_id, artifact_id)
        shortlist = prefilter_candidates(claim_body, candidates)

        created: list[Event] = []
        for past in shortlist:
            past_outcome = self._claim_status_of(past)
            # Defensive: prefilter operates on the already-filtered candidate
            # set, so this should always be survived/killed.
            if past_outcome not in _GRILLED_STATUSES:
                continue

            # 判例注入: the ruling verdict's death cause + rationale +
            # revival condition ride along so the reviewer can weigh HOW the
            # past claim died (a taste kill + a similar current claim ≠ hard
            # contradiction). Legacy verdicts inject as "unclassified".
            precedent = self._precedent_of(past)
            system, user = build_contradiction_prompt(
                claim_body,
                past.body,
                past_outcome,
                past_death_cause=precedent.death_cause if precedent else None,
                past_rationale=precedent.rationale if precedent else "",
                past_revival_condition=(
                    precedent.revival_condition if precedent else None
                ),
            )
            result = self._llm.complete_json(system, user)

            if not result.get("contradicts"):
                continue
            tension_type = result.get("tension_type", "")
            if not include_soft and tension_type == "soft":
                continue

            event = make_event(
                type=CHALLENGE,
                actor="system",
                confirmed=False,
                target_ref=claim_id,
                payload={
                    "kind": "lens_contradiction",
                    "question": result.get("question", ""),
                    "past_claim_id": past.id,
                    "past_artifact_id": past.artifact_ids[0],
                    "past_outcome": past_outcome,
                    "tension_type": tension_type,
                    "tension": result.get("tension", ""),
                    "auto_generated": True,
                },
            )
            created.append(self._event_service.append_event(artifact_id, event))

        return created

    # ------------------------------------------------------------------
    # Taste anchor (Lens 第二刀 / 品味锚)
    # ------------------------------------------------------------------

    async def assess_taste(
        self, artifact_id: str, claim_id: str, claim_body: str
    ) -> list[Event]:
        """Position the current claim on the taste/worth axis (品味锚).

        Anchors the claim to two facts — its NOVELTY position relative to real
        literature, and its TASTE/WORTH position relative to the user's OWN
        grilled kill/survive history — and surfaces ONE aggregate pending
        ``CHALLENGE`` (``payload.kind="taste"``) carrying a 4-tier rubric verdict.

        Anti-sycophancy is enforced STRUCTURALLY (we do not trust the model):

        - **History is the gate (Q-G)**: no grilled history → ``return []``
          (silent cold-start; the only legitimate taste source is the user's
          own trajectory — never field consensus).
        - **Literature is optional (degraded)**: an empty literature search still
          surfaces a verdict, anchored to history alone.
        - **No-anchor-no-verdict**: the model's anchors are FILTERED to those
          that match a real returned paper / shortlisted past claim; if BOTH
          anchor lists are empty after filtering → ``return []``.

        NEVER gates/modifies claim status; NEVER emits a numeric/absolute score
        (取证不定见 + taste 打分红线).

        Raises ``LLMNotConfiguredError`` if no LLM client is injected and
        ``ValueError`` if the current artifact cannot be resolved.
        """
        if self._llm is None:
            raise LLMNotConfiguredError("LLM client not configured")

        artifact = self._repo.get_artifact(artifact_id)
        if artifact is None:
            raise ValueError(f"Artifact {artifact_id!r} not found")
        library_id = artifact.library_id

        # History anchor — the GATE. No grilled history → silent (Q-G).
        candidates = self._grilled_candidates(library_id, claim_id, artifact_id)
        shortlist = prefilter_candidates(claim_body, candidates)
        if not shortlist:
            return []

        shortlist_ids = {past.id for past in shortlist}
        # 判例注入: each history anchor carries its verdict's 四元组 (outcome +
        # death cause + rationale + revival condition) — a not_worth kill is
        # the strongest revealed-taste signal the prompt can cite.
        past_claims: list[ClaimPrecedent] = []
        for past in shortlist:
            precedent = self._precedent_of(past)
            past_claims.append(
                ClaimPrecedent(
                    body=past.body,
                    outcome=self._claim_status_of(past),
                    claim_id=past.id,
                    death_cause=precedent.death_cause if precedent else None,
                    rationale=precedent.rationale if precedent else "",
                    revival_condition=(
                        precedent.revival_condition if precedent else None
                    ),
                )
            )

        # Literature anchor — OPTIONAL. May degrade to [] (history present).
        papers = await search_openalex(
            claim_body, max_results=5, mailto=_load_contact_email()
        )
        paper_titles = {p.get("title", "") for p in papers if p.get("title")}

        system, user = build_taste_prompt(claim_body, papers, past_claims)
        result = self._llm.complete_json(system, user)

        # Validate tier; anything off-rubric = no verdict.
        tier = result.get("tier")
        if tier not in _TASTE_TIERS:
            return []

        # Structural anchor filtering — drop hallucinated anchors. A real anchor
        # must cite a paper title that was actually returned, or a past_claim_id
        # that is actually in the shortlist.
        anchored_papers = [
            ap
            for ap in (result.get("anchored_papers") or [])
            if isinstance(ap, dict) and ap.get("title") in paper_titles
        ]
        anchored_claims = [
            ac
            for ac in (result.get("anchored_claims") or [])
            if isinstance(ac, dict) and ac.get("past_claim_id") in shortlist_ids
        ]

        # No-anchor-no-verdict: a taste verdict must cite ≥1 real anchor.
        if not anchored_papers and not anchored_claims:
            return []

        event = make_event(
            type=CHALLENGE,
            actor="system",
            confirmed=False,
            target_ref=claim_id,
            payload={
                "kind": "taste",
                "tier": tier,
                "reasoning": result.get("reasoning", ""),
                "anchored_papers": anchored_papers,
                "anchored_claims": anchored_claims,
                "question": result.get("question", ""),
                "auto_generated": True,
            },
        )
        return [self._event_service.append_event(artifact_id, event)]

    # ------------------------------------------------------------------
    # Semantic edges (Lens 第三刀 / ③ 可查询语料 — Tier 1, persistent graph)
    # ------------------------------------------------------------------

    async def compute_semantic_edges(self, library_id: str) -> list[Event]:
        """Lazily compute LLM-typed semantic edges over the Library's grilled
        claims and persist each as a ``LINK`` event (Tier 1, 持久语义图).

        This is the WRITE-action half of ③: it is NOT part of the corpus_graph
        projection (which stays a pure read of recorded LINK events). The
        frontend calls this before fetching the graph.

        Grilled-only: only claims with a confirmed survive/kill verdict
        participate (PARK/open claims get NO semantic edges — 只吃 grilled
        trajectory). Candidate pairs are bounded by the existing lexical
        prefilter.

        Compute-once: existing LINK pairs (directed ``(source, target)``) are
        gathered up front; any candidate already linked FROM a given claim is
        skipped, so re-running is idempotent and cheap.

        Each returned edge is validated — ``edge_type`` must be one of the four
        legal semantic types and ``target_claim_id`` must be a real provided
        candidate id (hallucinated ids/types are dropped). A surviving edge is
        appended as a ``LINK`` event on the source claim's artifact stream, born
        ``confirmed=True`` (an edge is a 取证 fact, not a 定见) and retractable.
        NEVER gates or modifies claim status.

        Returns the list of created ``LINK`` events (may be empty). Raises
        ``LLMNotConfiguredError`` if no LLM client is injected.
        """
        if self._llm is None:
            raise LLMNotConfiguredError("LLM client not configured")

        grilled = self._grilled_claims(library_id)
        by_id = {c.id: c for c in grilled}

        # Compute-once: existing directed (source, target) pairs that already
        # carry ANY LINK across the whole Library — skip recomputing them.
        existing_pairs: set[tuple[str, str]] = set()
        scanned_artifacts: set[str] = set()
        for claim in grilled:
            artifact_id = claim.artifact_ids[0]
            if artifact_id in scanned_artifacts:
                continue
            scanned_artifacts.add(artifact_id)
            for e in self._store.get_events(artifact_id):
                if e.type != LINK:
                    continue
                src = e.payload.get("source_claim_id")
                tgt = e.payload.get("target_claim_id")
                if src and tgt:
                    existing_pairs.add((src, tgt))

        created: list[Event] = []
        for current in grilled:
            others = [c for c in grilled if c.id != current.id]
            cands = prefilter_candidates(current.body, others)
            cands = [c for c in cands if (current.id, c.id) not in existing_pairs]
            if not cands:
                continue

            cand_ids = {c.id for c in cands}
            system, user = build_semantic_edges_prompt(
                current.body, [(c.body, c.id) for c in cands]
            )
            result = self._llm.complete_json(system, user)

            for edge in result.get("edges") or []:
                if not isinstance(edge, dict):
                    continue
                target_claim_id = edge.get("target_claim_id")
                edge_type = edge.get("edge_type")
                # Drop hallucinated edges: unknown type or non-candidate target.
                if edge_type not in _SEMANTIC_EDGE_TYPES:
                    continue
                if target_claim_id not in cand_ids or target_claim_id not in by_id:
                    continue
                pair = (current.id, target_claim_id)
                if pair in existing_pairs:
                    continue
                existing_pairs.add(pair)
                link = make_event(
                    type=LINK,
                    actor="system",
                    confirmed=True,
                    target_ref=current.id,
                    payload={
                        "source_claim_id": current.id,
                        "target_claim_id": target_claim_id,
                        "edge_type": edge_type,
                        "reason": edge.get("reason", ""),
                        "auto_generated": True,
                    },
                )
                created.append(
                    self._event_service.append_event(current.artifact_ids[0], link)
                )

        return created

    # ------------------------------------------------------------------
    # Candidate enumeration
    # ------------------------------------------------------------------

    def _grilled_claims(self, library_id: str) -> list:
        """All Library claims with a confirmed survive/kill verdict.

        The grilled trajectory — the only corpus the Lens eats (PARK/open
        claims never qualify). Claims with no parking artifact are skipped
        (cannot resolve a status without an event stream).
        """
        out = []
        for claim in self._repo.list_claims(library_id):
            if not claim.artifact_ids:
                continue
            if self._claim_status_of(claim) in _GRILLED_STATUSES:
                out.append(claim)
        return out

    def _grilled_candidates(
        self, library_id: str, claim_id: str, artifact_id: str
    ) -> list:
        """Grilled Library claims, excluding the current claim/artifact.

        Builds on ``_grilled_claims`` and drops the current claim and any claim
        belonging to the current artifact.
        """
        return [
            claim
            for claim in self._grilled_claims(library_id)
            if claim.id != claim_id and artifact_id not in claim.artifact_ids
        ]

    def _claim_status_of(self, claim) -> str:
        """Resolve a claim's status from its parking artifact's event stream.

        First-cut model: ``claim.artifact_ids[0]`` is the parking artifact (one
        claim ⇄ one artifact). ``claim_status`` already excludes PARK/open and
        folds back retracted verdicts, so no retract special-casing is needed.
        """
        events = self._store.get_events(claim.artifact_ids[0])
        return claim_status(events, claim.id)

    def _precedent_of(self, claim) -> VerdictPrecedent | None:
        """判例 of the claim's ruling verdict (same stream as its status).

        Pure read via ``verdict_precedent``; only confirmed, non-retracted
        verdicts count, so the injected rationale is always human-signed.
        None for claims without a ruling verdict; legacy verdicts yield a
        precedent whose death_cause is None (投影语义: 未分类).
        """
        events = self._store.get_events(claim.artifact_ids[0])
        return verdict_precedent(events, claim.id)

    # ------------------------------------------------------------------
    # Corpus graph (Lens 第三刀 / ③ 可查询语料 — Tier 0)
    # ------------------------------------------------------------------

    def corpus_graph(self, library_id: str) -> CorpusGraph:
        """Build the Library's corpus graph from existing events (PURE READ).

        Tier 0 — ZERO LLM, ZERO persistence, ZERO embedding. Computed on the
        fly like every other projection. The PULL counterpart to ①②: the user
        queries their own corpus as a graph of claim/material nodes joined by
        CONFIRMED structural edges.

        Nodes:
        - One ``claim`` node per Library claim that has a parking artifact
          (``claim.artifact_ids[0]``); label = body, status = ``claim_status``.
        - One ``material`` node per material that a confirmed GROUND edge points
          at (added lazily; skipped if the material can't be resolved).

        Edges (取证不定见 / Q-5 — CONFIRMED relations only):
        - ``contradicts``: a CONFIRMED, non-retracted ② ``lens_contradiction``
          CHALLENGE → ``current_claim —contradicts→ past_claim``.
        - ``grounds``: a CONFIRMED, non-retracted GROUND whose stance is
          ``supports`` (three-state ``verdict`` OR legacy ``supported: True``)
          → ``claim —grounds→ material``.
        - ``undermines``: a CONFIRMED, non-retracted GROUND whose verdict is
          ``contradicts`` → ``material —undermines→ claim``. Deterministic
          counter-evidence edge — pure read of the ground payload, zero new
          storage. ``silent`` grounds produce NO edge (查无 relates nothing),
          and legacy ``supported: False`` (未分态) produces NO edge either —
          we never guess it into either camp.
        - ``narrowed_from``: a CONFIRMED, non-retracted kill VERDICT whose
          payload names a ``successor_claim_id`` (划界死 / boundary kill) →
          ``successor —narrowed_from→ killed claim``. Deterministic source —
          read straight off the verdict payload, never LLM-computed, and no
          new LINK event type (zero new storage).

        Pending/unconfirmed/retracted contradictions and grounds produce NO
        edges. Edges whose endpoint node isn't in the graph (e.g. a
        ``past_claim_id`` pointing outside this Library) are dropped. Identical
        edges are deduped. Output is sorted deterministically.
        """
        # --- Claim nodes (and the set of artifact streams to scan) ---
        claim_ids: set[str] = set()
        artifact_ids: set[str] = set()
        nodes: dict[str, GraphNode] = {}

        for claim in self._repo.list_claims(library_id):
            if not claim.artifact_ids:
                continue
            artifact_id = claim.artifact_ids[0]
            artifact_ids.add(artifact_id)
            claim_ids.add(claim.id)
            nodes[claim.id] = GraphNode(
                id=claim.id,
                type="claim",
                label=claim.body,
                status=claim_status(self._store.get_events(artifact_id), claim.id),
            )

        # --- Edges: scan each artifact's event stream, confirmed-only ---
        edge_keys: set[tuple[str, str, str]] = set()
        edges: list[GraphEdge] = []

        def _add_edge(source: str, target: str, etype: str) -> None:
            key = (source, target, etype)
            if key in edge_keys:
                return
            edge_keys.add(key)
            edges.append(GraphEdge(source=source, target=target, type=etype))

        for artifact_id in artifact_ids:
            events = self._store.get_events(artifact_id)
            confirmed = _confirmed_event_ids(events)
            retracted = retracted_event_ids(events)
            for e in events:
                # An event "counts" iff confirmed AND not retracted (Q-5).
                if not (e.confirmed or e.id in confirmed):
                    continue
                if e.id in retracted:
                    continue

                if e.type == CHALLENGE and e.payload.get("kind") == "lens_contradiction":
                    source = e.target_ref
                    target = e.payload.get("past_claim_id")
                    if source is None or target is None:
                        continue
                    # Drop dangling: both endpoints must be claim nodes in scope.
                    if source not in claim_ids or target not in claim_ids:
                        continue
                    _add_edge(source, target, "contradicts")

                elif e.type == GROUND:
                    # Three-state stance decides the edge (决策 4):
                    #   supports (+legacy True) → claim —grounds→ material
                    #   contradicts            → material —undermines→ claim
                    #   silent / legacy False (未分态) / unknown → NO edge
                    stance = ground_stance(e.payload)
                    if stance not in ("supports", "contradicts"):
                        continue
                    claim_id = e.target_ref
                    material_id = e.payload.get("material_id")
                    if claim_id is None or not material_id:
                        continue
                    if claim_id not in claim_ids:
                        continue
                    # Ensure a material node exists (skip if unresolvable).
                    if material_id not in nodes:
                        material = self._repo.get_material(material_id)
                        if material is None:
                            continue
                        label = material.payload.get("title", "") or str(
                            material.provenance
                        )
                        nodes[material_id] = GraphNode(
                            id=material_id, type="material", label=label
                        )
                    if stance == "supports":
                        _add_edge(claim_id, material_id, "grounds")
                    else:
                        _add_edge(material_id, claim_id, "undermines")

                elif e.type == VERDICT:
                    # 死因分诊: a boundary kill may name the narrowed claim
                    # that lives on. Deterministic lineage edge — pure read of
                    # the verdict payload (never LLM). Legacy verdicts have no
                    # successor_claim_id and simply produce nothing.
                    if e.payload.get("outcome") != "kill":
                        continue
                    successor = e.payload.get("successor_claim_id")
                    dead = e.target_ref
                    if not successor or dead is None:
                        continue
                    # Drop dangling: both endpoints must be claim nodes in scope.
                    if successor not in claim_ids or dead not in claim_ids:
                        continue
                    _add_edge(successor, dead, "narrowed_from")

                elif e.type == LINK:
                    # Tier 1 LLM-computed semantic edge (builds_on / depends_on
                    # / shares_method / shares_gap). corpus_graph stays a PURE
                    # READ projection — it does NOT compute these, only reads
                    # recorded LINK events under the same confirmed-only +
                    # retracted filter + drop-dangling + dedupe discipline.
                    source = e.payload.get("source_claim_id")
                    target = e.payload.get("target_claim_id")
                    etype = e.payload.get("edge_type")
                    if not source or not target or etype not in _SEMANTIC_EDGE_TYPES:
                        continue
                    # Drop dangling: both endpoints must be claim nodes in scope.
                    if source not in claim_ids or target not in claim_ids:
                        continue
                    _add_edge(source, target, etype)

        sorted_nodes = sorted(nodes.values(), key=lambda n: (n.type, n.id))
        sorted_edges = sorted(edges, key=lambda x: (x.source, x.target, x.type))
        return CorpusGraph(nodes=sorted_nodes, edges=sorted_edges)
