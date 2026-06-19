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
from anneal.llm.prompts import build_contradiction_prompt
from anneal.services.event_service import EventService
from anneal.store.event_store import EventStore
from anneal.store.repository import Repository

# Past-claim outcomes that qualify as grilled trajectory (candidate set).
_GRILLED_STATUSES = {"survived", "killed"}


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
