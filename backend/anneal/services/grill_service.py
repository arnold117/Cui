"""Grill service — adversarial questioning loop.

Implements PARK -> GRILL transition and the challenge-answer-verdict cycle.
从零开始拷问，无偷渡 — park content becomes context but grill starts fresh.

Uses EventService for event writes; confirmation is a cross-cutting concern
handled by EventService.confirm_event / retract_event.

Dependency: EventStore -> EventService -> GrillService.
"""

from __future__ import annotations

from anneal.domain.constants import SUPPORTED_ARTIFACT_KINDS
from anneal.domain.events import (
    ANSWER,
    CHALLENGE,
    PARK,
    VERDICT,
    Event,
    make_event,
)
from anneal.domain.projections import has_grill_events, is_parked
from anneal.llm.client import LLMClient
from anneal.llm.errors import LLMNotConfiguredError, LLMResponseError
from anneal.services.event_service import EventService
from anneal.store.event_store import EventStore


class GrillService:
    """Adversarial grill loop for artifacts.

    Supported artifact kinds are validated at the service layer (spec §2.4:
    "泛化抽象，不泛化实现" — schema is generic, implementation is narrow).
    """

    def __init__(self, store: EventStore, event_service: EventService, llm: LLMClient | None = None) -> None:
        self._store = store
        self._event_service = event_service
        self._llm = llm

    # ------------------------------------------------------------------
    # Transition gate
    # ------------------------------------------------------------------

    def start_grill(self, artifact_id: str, kind: str) -> None:
        """Validate that the artifact can enter GRILL from PARK.

        This is a validation-only gate — it does NOT emit its own event.
        The first challenge() IS the start of grill.

        Raises ValueError if:
        - kind is not in SUPPORTED_KINDS
        - artifact has no events (never parked)
        - artifact has no park event
        - artifact already has grill events (already grilling)
        """
        if kind not in SUPPORTED_ARTIFACT_KINDS:
            raise ValueError(
                f"Unsupported artifact kind {kind!r}; "
                f"supported: {sorted(SUPPORTED_ARTIFACT_KINDS)}"
            )

        events = self._store.get_events(artifact_id)

        if not events:
            raise ValueError(
                f"Artifact {artifact_id!r} has no events — cannot grill an unparked artifact"
            )

        if not any(e.type == PARK for e in events):
            raise ValueError(
                f"Artifact {artifact_id!r} was never parked — must park before grilling"
            )

        if has_grill_events(events):
            raise ValueError(
                f"Artifact {artifact_id!r} already has grill events — cannot start_grill again"
            )

    # ------------------------------------------------------------------
    # Internal validation helpers
    # ------------------------------------------------------------------

    def _assert_artifact_was_parked(self, artifact_id: str) -> list[Event]:
        """Return events for artifact_id, raising if empty or never parked."""
        events = self._store.get_events(artifact_id)
        if not events:
            raise ValueError(
                f"Artifact {artifact_id!r} has no events"
            )
        if not any(e.type == PARK for e in events):
            raise ValueError(
                f"Artifact {artifact_id!r} was never parked"
            )
        return events

    def _assert_has_challenge(self, artifact_id: str) -> list[Event]:
        """Return events for artifact_id, raising if no CHALLENGE exists yet."""
        events = self._store.get_events(artifact_id)
        if not any(e.type == CHALLENGE for e in events):
            raise ValueError(
                f"No challenge exists for artifact {artifact_id!r} "
                "— cannot answer/verdict/bypass before first challenge"
            )
        return events

    # ------------------------------------------------------------------
    # Grill actions
    # ------------------------------------------------------------------

    def challenge(self, artifact_id: str, claim_id: str, question: str) -> Event:
        """System poses a challenge. Appends CHALLENGE event.

        actor="system", confirmed=False (system action needs user confirmation,
        spec §2.6 decision #2).
        target_ref=claim_id.

        Validates:
        - Artifact has events (was created).
        - Artifact has a park event (was parked).
        - Allowed on parked-only OR already-grilling artifacts.
        """
        self._assert_artifact_was_parked(artifact_id)
        event = make_event(
            type=CHALLENGE,
            actor="system",
            confirmed=False,
            target_ref=claim_id,
            payload={"question": question},
        )
        return self._event_service.append_event(artifact_id, event)

    def answer(self, artifact_id: str, claim_id: str, response: str) -> Event:
        """User answers a challenge. Appends ANSWER event.

        actor="user", confirmed=True (user doing it IS confirmation).
        target_ref=claim_id.

        Validates: at least one CHALLENGE event must exist.
        """
        self._assert_has_challenge(artifact_id)
        event = make_event(
            type=ANSWER,
            actor="user",
            confirmed=True,
            target_ref=claim_id,
            payload={"response": response},
        )
        return self._event_service.append_event(artifact_id, event)

    def verdict(
        self,
        artifact_id: str,
        claim_id: str,
        outcome: str,
        rationale: str,
    ) -> Event:
        """Judge verdict on a claim. Appends VERDICT event.

        outcome must be "survive" or "kill".
        actor="system", confirmed=False (system judgment needs user confirmation).
        target_ref=claim_id.
        Killed ideas permanently remain in trajectory.

        Validates: at least one CHALLENGE event must exist.
        """
        self._assert_has_challenge(artifact_id)
        if outcome not in ("survive", "kill"):
            raise ValueError(
                f"Verdict outcome must be 'survive' or 'kill', got {outcome!r}"
            )
        event = make_event(
            type=VERDICT,
            actor="system",
            confirmed=False,
            target_ref=claim_id,
            payload={"outcome": outcome, "rationale": rationale},
        )
        return self._event_service.append_event(artifact_id, event)

    def bypass(self, artifact_id: str, claim_id: str) -> Event:
        """Skip grill for a claim, mark debt=True.

        Appends VERDICT event with outcome="survive", debt=True, confirmed=False.
        Debt must be repaid (confirmed) before promote/export/reference.

        Validates: at least one CHALLENGE event must exist.
        """
        self._assert_has_challenge(artifact_id)
        event = make_event(
            type=VERDICT,
            actor="system",
            confirmed=False,
            debt=True,
            target_ref=claim_id,
            payload={"outcome": "survive", "rationale": "bypass — debt incurred"},
        )
        return self._event_service.append_event(artifact_id, event)

    # ------------------------------------------------------------------
    # Auto-grill (LLM-powered)
    # ------------------------------------------------------------------

    def auto_challenge(self, artifact_id: str, claim_id: str, claim_body: str, context: str = "") -> Event:
        """LLM-generated challenge. confirmed=False per spec §2.6."""
        if self._llm is None:
            raise LLMNotConfiguredError("LLM client not configured")
        from anneal.llm.prompts import build_challenge_prompt
        self._assert_artifact_was_parked(artifact_id)
        system, user = build_challenge_prompt(claim_body, context)
        result = self._llm.complete_json(system, user)
        question = result.get("question", "")
        if not question:
            raise LLMResponseError("LLM returned empty challenge question")
        event = make_event(
            type=CHALLENGE, actor="system", confirmed=False,
            target_ref=claim_id,
            payload={"question": question, "target_aspect": result.get("target_aspect", ""), "auto_generated": True},
        )
        return self._event_service.append_event(artifact_id, event)

    def auto_verdict(self, artifact_id: str, claim_id: str, claim_body: str, question: str, answer: str) -> Event:
        """LLM-generated verdict. confirmed=False per spec §2.6."""
        if self._llm is None:
            raise LLMNotConfiguredError("LLM client not configured")
        from anneal.llm.prompts import build_verdict_prompt
        self._assert_has_challenge(artifact_id)
        system, user = build_verdict_prompt(claim_body, question, answer)
        result = self._llm.complete_json(system, user)
        outcome = result.get("outcome", "")
        if outcome not in ("survive", "kill"):
            raise LLMResponseError(f"LLM returned invalid verdict outcome: {outcome!r}")
        event = make_event(
            type=VERDICT, actor="system", confirmed=False,
            target_ref=claim_id,
            payload={"outcome": outcome, "rationale": result.get("rationale", ""), "confidence": result.get("confidence", 0.0), "auto_generated": True},
        )
        return self._event_service.append_event(artifact_id, event)
