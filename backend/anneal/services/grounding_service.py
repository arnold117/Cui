"""Grounding service — the explicit, human-in-loop literature grounding step.

Stage 2 of the literature-search slice. The user has already collected papers
(Stage 1: ``Material(kind="paper")`` + ``collect_material`` events). Grounding
judges whether a specific collected paper SUPPORTS a specific claim, and emits a
PENDING ``ground`` event that the user later confirms through the existing
confirm gate. Once confirmed, grounded evidence feeds the Lens.

Mirrors ``GrillService``'s shape: constructor ``(store, event_service, llm)``;
a ``_assert_artifact_was_parked`` guard; a manual method (no LLM) and an
LLM-assisted method that guards on ``self._llm is None``, calls a
``build_*_prompt``, calls ``self._llm.complete_json``, validates the result,
and appends a ``confirmed=False`` event via ``self._event_service``.

Dependency: EventStore -> EventService -> GroundingService; Repository supplies
the collected Material.
"""

from __future__ import annotations

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
    def _coerce_supported(result: dict) -> bool:
        """Coerce a 'boolean-ish' supported value to bool.

        Accepts real bools and common string spellings. Raises
        LLMResponseError if the key is missing or not usable — we never
        silently default a missing judgment to False.
        """
        if "supported" not in result:
            raise LLMResponseError(
                f"LLM result lacks a 'supported' key: {result!r}"
            )
        value = result["supported"]
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "yes", "1"):
                return True
            if lowered in ("false", "no", "0"):
                return False
        raise LLMResponseError(
            f"LLM returned an unusable 'supported' value: {value!r}"
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
        supported: bool,
        evidence: str = "",
        assessment: str = "",
    ) -> Event:
        """Manual grounding — explicit user-supplied judgment (no LLM).

        Emits a PENDING (confirmed=False) GROUND event targeting the claim.
        The user confirms it through the existing confirm gate.
        """
        material = self._get_material(material_id)
        self._assert_artifact_was_parked(artifact_id)
        event = make_event(
            type=GROUND,
            actor="user",
            confirmed=False,
            target_ref=claim_id,
            payload={
                "material_id": material_id,
                "supported": supported,
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
        supported = self._coerce_supported(result)
        event = make_event(
            type=GROUND,
            # LLM-generated suggestion (user confirms via the gate) — mirrors
            # grill auto_challenge/auto_verdict which are actor="system".
            actor="system",
            confirmed=False,
            target_ref=claim_id,
            payload={
                "material_id": material_id,
                "supported": supported,
                "evidence": result.get("evidence", ""),
                "assessment": result.get("assessment", ""),
                "source": material.provenance.get("source", ""),
                "title": material.payload.get("title", ""),
                "auto_generated": True,
            },
        )
        return self._event_service.append_event(artifact_id, event)
