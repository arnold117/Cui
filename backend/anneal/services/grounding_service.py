"""Grounding service — the explicit, human-in-loop literature grounding step.

Stage 2 of the literature-search slice. The user has already collected papers
(Stage 1: ``Material(kind="paper")`` + ``collect_material`` events). Grounding
judges how a specific collected paper bears on a specific claim — a three-state
``verdict`` (supports / contradicts / silent, see ``GROUND_VERDICTS``): 「文献
没谈这个 claim」和「文献打这个 claim」是两个完全不同的状态, and 查无 (silent)
is a legitimate first-class output, not a failure. The service emits a PENDING
``ground`` event that the user later confirms through the existing confirm
gate. Once confirmed, grounded evidence feeds the Lens — and a confirmed
``contradicts`` ground additionally surfaces a pending ``evidence_contradiction``
CHALLENGE at the confirm gate (see ``EventService.confirm_event`` — 负证据是
一等公民, 取证不定见).

Legacy events carry only ``supported: bool``; new events write only
``verdict``. Read-side compatibility lives in ``ground_stance``.

Mirrors ``GrillService``'s shape: constructor ``(store, event_service, llm)``;
a ``_assert_artifact_was_parked`` guard; a manual method (no LLM) and an
LLM-assisted method that guards on ``self._llm is None``, calls a
``build_*_prompt``, calls ``self._llm.complete_json``, validates the result,
and appends a ``confirmed=False`` event via ``self._event_service``.

Dependency: EventStore -> EventService -> GroundingService; Repository supplies
the collected Material.
"""

from __future__ import annotations

from anneal.domain.constants import GROUND_VERDICTS
from anneal.domain.events import GROUND, PARK, Event, make_event
from anneal.llm.client import LLMClient
from anneal.llm.errors import LLMNotConfiguredError, LLMResponseError
from anneal.services.event_service import EventService
from anneal.store.event_store import EventStore
from anneal.store.repository import Repository


class GroundingService:
    """Grounds claims against collected literature (Materials)."""

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

    # ------------------------------------------------------------------
    # Internal validation helpers (mirror GrillService)
    # ------------------------------------------------------------------

    def _assert_artifact_was_parked(self, artifact_id: str) -> list[Event]:
        """Return events for artifact_id, raising if empty or never parked."""
        events = self._store.get_events(artifact_id)
        if not events:
            raise ValueError(f"Artifact {artifact_id!r} has no events")
        if not any(e.type == PARK for e in events):
            raise ValueError(f"Artifact {artifact_id!r} was never parked")
        return events

    @staticmethod
    def _coerce_verdict(result: dict) -> str:
        """Coerce the LLM's three-state grounding verdict.

        Accepts only the three legal states (supports / contradicts /
        silent), case-insensitively for string sloppiness. Raises
        LLMResponseError if the key is missing or the value is off-enum —
        we never silently default a missing judgment, and we never map an
        unusable answer onto any state (fail-loud, 绝不静默默认).
        """
        if "verdict" not in result:
            raise LLMResponseError(
                f"LLM result lacks a 'verdict' key: {result!r}"
            )
        value = result["verdict"]
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in GROUND_VERDICTS:
                return lowered
        raise LLMResponseError(
            f"LLM returned an unusable grounding 'verdict' value: {value!r}; "
            f"must be one of {sorted(GROUND_VERDICTS)}"
        )

    def _get_material(self, material_id: str):
        material = self._repo.get_material(material_id)
        if material is None:
            raise ValueError(f"Material {material_id!r} not found")
        return material

    # ------------------------------------------------------------------
    # Grounding actions
    # ------------------------------------------------------------------

    def ground(
        self,
        artifact_id: str,
        claim_id: str,
        material_id: str,
        verdict: str,
        evidence: str = "",
        assessment: str = "",
    ) -> Event:
        """Manual grounding — explicit user-supplied judgment (no LLM).

        ``verdict`` must be one of ``GROUND_VERDICTS`` (supports /
        contradicts / silent) — new events write ONLY the three-state
        ``verdict`` field, never the legacy ``supported`` bool. Emits a
        PENDING (confirmed=False) GROUND event targeting the claim. The user
        confirms it through the existing confirm gate.
        """
        if verdict not in GROUND_VERDICTS:
            raise ValueError(
                f"Unknown grounding verdict {verdict!r}; "
                f"must be one of {sorted(GROUND_VERDICTS)}"
            )
        material = self._get_material(material_id)
        self._assert_artifact_was_parked(artifact_id)
        event = make_event(
            type=GROUND,
            actor="user",
            confirmed=False,
            target_ref=claim_id,
            payload={
                "material_id": material_id,
                "verdict": verdict,
                "evidence": evidence,
                "assessment": assessment,
                "source": material.provenance.get("source", ""),
                "title": material.payload.get("title", ""),
            },
        )
        return self._event_service.append_event(artifact_id, event)

    def auto_ground(
        self,
        artifact_id: str,
        claim_id: str,
        claim_body: str,
        material_id: str,
    ) -> Event:
        """LLM-assisted grounding. confirmed=False — user confirms later."""
        if self._llm is None:
            raise LLMNotConfiguredError("LLM client not configured")
        material = self._get_material(material_id)
        self._assert_artifact_was_parked(artifact_id)
        from anneal.llm.prompts import build_grounding_prompt

        system, user = build_grounding_prompt(
            claim_body,
            material.payload.get("title", ""),
            material.payload.get("abstract", ""),
        )
        result = self._llm.complete_json(system, user)
        verdict = self._coerce_verdict(result)
        event = make_event(
            type=GROUND,
            # LLM-generated suggestion (user confirms via the gate) — mirrors
            # grill auto_challenge/auto_verdict which are actor="system".
            actor="system",
            confirmed=False,
            target_ref=claim_id,
            payload={
                "material_id": material_id,
                "verdict": verdict,
                "evidence": result.get("evidence", ""),
                "assessment": result.get("assessment", ""),
                "source": material.provenance.get("source", ""),
                "title": material.payload.get("title", ""),
                "auto_generated": True,
            },
        )
        return self._event_service.append_event(artifact_id, event)
