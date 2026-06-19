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

from anneal.domain.events import CHALLENGE, Event, make_event
from anneal.domain.projections import claim_status
from anneal.lens.prefilter import prefilter_candidates
from anneal.llm.client import LLMClient
from anneal.llm.errors import LLMNotConfiguredError
from anneal.llm.prompts import build_contradiction_prompt, build_taste_prompt
from anneal.search.openalex import search_openalex
from anneal.services.collect_service import _load_contact_email
from anneal.services.event_service import EventService
from anneal.store.event_store import EventStore
from anneal.store.repository import Repository

# Past-claim outcomes that qualify as grilled trajectory (candidate set).
_GRILLED_STATUSES = {"survived", "killed"}

# The four taste rubric tiers (spec §2). Anything else = no verdict.
_TASTE_TIERS = {"replication", "incremental", "novel_but_tasteless", "tasteful"}


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

            system, user = build_contradiction_prompt(
                claim_body, past.body, past_outcome
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
        past_claims: list[tuple[str, str, str]] = [
            (past.body, self._claim_status_of(past), past.id) for past in shortlist
        ]

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
    # Candidate enumeration
    # ------------------------------------------------------------------

    def _grilled_candidates(
        self, library_id: str, claim_id: str, artifact_id: str
    ) -> list:
        """Library claims with a confirmed survive/kill verdict.

        Excludes the current claim and any claim belonging to the current
        artifact. Claims with no parking artifact are skipped (cannot resolve a
        status without an event stream).
        """
        out = []
        for claim in self._repo.list_claims(library_id):
            if claim.id == claim_id:
                continue
            if not claim.artifact_ids:
                continue
            if artifact_id in claim.artifact_ids:
                continue
            if self._claim_status_of(claim) in _GRILLED_STATUSES:
                out.append(claim)
        return out

    def _claim_status_of(self, claim) -> str:
        """Resolve a claim's status from its parking artifact's event stream.

        First-cut model: ``claim.artifact_ids[0]`` is the parking artifact (one
        claim ⇄ one artifact). ``claim_status`` already excludes PARK/open and
        folds back retracted verdicts, so no retract special-casing is needed.
        """
        events = self._store.get_events(claim.artifact_ids[0])
        return claim_status(events, claim.id)
