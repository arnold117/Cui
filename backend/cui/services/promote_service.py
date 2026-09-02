"""Promote service — moves survived claims from GRILL into DOC projection.

Uses EventService for debt clearance (confirm/retract); does NOT own
confirm_event itself.

Dependency: EventStore -> EventService -> PromoteService.
"""

from __future__ import annotations

from cui.domain.events import PROMOTE, Event, make_event
from cui.domain.invariants import assert_can_promote, assert_claim_no_debt
from cui.domain.projections import doc_projection
from cui.services.event_service import EventService
from cui.store.event_store import EventStore


class PromoteService:
    def __init__(self, store: EventStore, event_service: EventService) -> None:
        self._store = store
        self._event_service = event_service

    def promote(self, artifact_id: str, claim_id: str) -> Event:
        """Promote a survived claim into DOC.

        Calls assert_can_promote (debt gate + survival check).
        Appends PROMOTE event. actor="user", confirmed=True (user action).
        """
        events = self._store.get_events(artifact_id)
        assert_can_promote(events, claim_id)
        evt = make_event(
            type=PROMOTE, actor="user", target_ref=claim_id, confirmed=True,
        )
        self._store.append(artifact_id, evt)
        return evt

    def reference_claim(self, artifact_id: str, claim_id: str) -> None:
        """Check that a claim can be referenced (no unresolved debt).

        Spec section 4 Q-D: hard-block on referencing a claim with debt.
        Does NOT append any event -- just validates.
        """
        events = self._store.get_events(artifact_id)
        assert_claim_no_debt(events, claim_id)

    def get_doc(self, artifact_id: str) -> list[Event]:
        """Return the DOC projection -- only verified, confirmed, debt-free,
        surviving content."""
        events = self._store.get_events(artifact_id)
        return doc_projection(events)
