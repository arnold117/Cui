"""Cross-cutting event service — confirm, retract, batch-confirm.

The human confirmation gate needed by ALL domain flows (grill confirmation,
edit batch confirmation, debt clearance).  Lives here rather than inside any
single domain service.

负证据反哺 (negative-evidence feedback) also lives AT the gate: confirming a
``contradicts`` GROUND event surfaces a pending ``evidence_contradiction``
CHALLENGE onto the claim's board. It sits here — not in a route or a UI
callback — because the gate is the single choke point every confirmation
passes through (``batch_confirm`` delegates to ``confirm_event``), so the
invariant "confirmed counter-evidence always challenges the claim" is
enforced structurally, 不靠自觉. Deterministic (zero LLM), and strictly
取证不定见: it only poses a question; it NEVER auto-verdicts from negative
evidence.

Dependency: EventStore → EventService → domain services.
"""

from __future__ import annotations

from anneal.domain.events import CHALLENGE, CONFIRM, GROUND, RETRACT, Event, make_event
from anneal.domain.projections import ground_stance
from anneal.domain.projections import pending_events as _pending
from anneal.store.event_store import EventStore


class EventService:
    def __init__(self, store: EventStore) -> None:
        self._store = store

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def append_event(self, artifact_id: str, event: Event) -> Event:
        """Append an event to the store. Returns the event."""
        self._store.append(artifact_id, event)
        return event

    def confirm_event(self, artifact_id: str, event_id: str) -> Event:
        """User confirms a pending event.

        Creates and appends a CONFIRM event targeting *event_id*.
        Raises ValueError if the target event_id does not exist in the stream.

        负证据反哺: when the confirmed target is a ``contradicts`` GROUND
        event, a pending ``evidence_contradiction`` CHALLENGE is surfaced on
        the claim (see ``_surface_evidence_contradiction``).
        """
        existing = self._store.get_events(artifact_id)
        target = next((e for e in existing if e.id == event_id), None)
        if target is None:
            raise ValueError(
                f"Event {event_id!r} not found in artifact {artifact_id!r}"
            )
        confirm = make_event(
            type=CONFIRM,
            actor="user",
            target_ref=event_id,
            confirmed=True,
        )
        self._store.append(artifact_id, confirm)
        self._surface_evidence_contradiction(artifact_id, target, existing)
        return confirm

    def _surface_evidence_contradiction(
        self, artifact_id: str, target: Event, existing: list[Event]
    ) -> Event | None:
        """Surface a confirmed ``contradicts`` GROUND as a pending CHALLENGE.

        The P1 对辩闭环 already feeds confirmed grounds back into
        auto_challenge/auto_verdict prompts (pull side); this is the PUSH
        side for counter-evidence: the moment the user signs a contradicts
        ground, the contradiction lands on the challenge-centric board as a
        first-class pending challenge (actor="system", confirmed=False —
        the user still confirms/retracts it like any challenge).

        Rules:
        - Only a three-state ``verdict: "contradicts"`` triggers. Legacy
          ``supported: False`` (未分态) NEVER does — we don't guess it into
          contradicts.
        - Deterministic payload/question straight off the ground event
          (material reference + evidence excerpt); zero LLM.
        - Idempotent: one challenge per ground event
          (``payload.ground_event_id``). A challenge the user already
          retracted stays dismissed — re-confirming never resurrects it.
        - 取证不定见: only a challenge, never a verdict.
        """
        if target.type != GROUND:
            return None
        if ground_stance(target.payload) != "contradicts":
            return None
        if target.target_ref is None:
            return None
        for e in existing:
            if (
                e.type == CHALLENGE
                and e.payload.get("kind") == "evidence_contradiction"
                and e.payload.get("ground_event_id") == target.id
            ):
                return None  # already surfaced (possibly resolved/retracted)
        p = target.payload
        title = p.get("title", "") or "未命名文献"
        question = f"你确认了一条反证：《{title}》与这条 claim 相抵触。"
        evidence = p.get("evidence", "")
        if evidence:
            question += f"证据摘录：{evidence}。"
        question += "这条 claim 如何回应这份文献？"
        challenge = make_event(
            type=CHALLENGE,
            actor="system",
            confirmed=False,
            target_ref=target.target_ref,
            payload={
                "kind": "evidence_contradiction",
                "question": question,
                "material_id": p.get("material_id", ""),
                "title": p.get("title", ""),
                "source": p.get("source", ""),
                "evidence": evidence,
                "assessment": p.get("assessment", ""),
                "ground_event_id": target.id,
                "auto_generated": True,
            },
        )
        self._store.append(artifact_id, challenge)
        return challenge

    def retract_event(self, artifact_id: str, event_id: str) -> Event:
        """User rejects an event.

        Creates and appends a RETRACT event targeting *event_id*.
        Raises ValueError if the target event_id does not exist in the stream.
        追加否定，不删历史.
        """
        existing = self._store.get_events(artifact_id)
        if not any(e.id == event_id for e in existing):
            raise ValueError(
                f"Event {event_id!r} not found in artifact {artifact_id!r}"
            )
        retract = make_event(
            type=RETRACT,
            actor="user",
            target_ref=event_id,
            confirmed=True,
        )
        self._store.append(artifact_id, retract)
        return retract

    def batch_confirm(self, artifact_id: str, event_ids: list[str]) -> list[Event]:
        """Batch confirmation (edit flow, spec §2.6 decision #5).

        Confirms multiple events at once — e.g. user clicks '完成编辑'
        and reviews all pending edit events' scope in one go.
        """
        results: list[Event] = []
        for event_id in event_ids:
            results.append(self.confirm_event(artifact_id, event_id))
        return results

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def pending_events(self, artifact_id: str) -> list[Event]:
        """List events awaiting user confirmation."""
        events = self._store.get_events(artifact_id)
        return _pending(events)
