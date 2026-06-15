"""Tests for anneal.services.event_service — human confirmation gate."""

import pytest

from anneal.domain.events import (
    ANSWER,
    CHALLENGE,
    CONFIRM,
    EDIT,
    RETRACT,
    VERDICT,
    make_event,
)
from anneal.services.event_service import EventService
from anneal.store.event_store import InMemoryEventStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ARTIFACT = "artifact-1"


@pytest.fixture
def store():
    return InMemoryEventStore()


@pytest.fixture
def svc(store):
    return EventService(store)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pending_event(**kw):
    """Create an unconfirmed event (pending user confirmation)."""
    return make_event(confirmed=False, **kw)


# ===========================================================================
# confirm_event
# ===========================================================================


class TestConfirmEvent:
    def test_appends_confirm_targeting_event_id(self, svc, store):
        """confirm_event creates a CONFIRM event whose target_ref is the original event_id."""
        original = _pending_event(type=CHALLENGE, actor="system")
        svc.append_event(ARTIFACT, original)

        confirm = svc.confirm_event(ARTIFACT, original.id)

        assert confirm.type == CONFIRM
        assert confirm.target_ref == original.id
        assert confirm.confirmed is True
        assert confirm.actor == "user"

        # Stored in the event stream.
        all_events = store.get_events(ARTIFACT)
        assert confirm in all_events

    def test_raises_on_nonexistent_event_id(self, svc):
        """confirm_event raises ValueError when the target event doesn't exist."""
        with pytest.raises(ValueError, match="not found in artifact"):
            svc.confirm_event(ARTIFACT, "no-such-event")

    def test_confirm_removes_from_pending(self, svc):
        """After confirming, the event is no longer in pending_events."""
        original = _pending_event(type=CHALLENGE, actor="system")
        svc.append_event(ARTIFACT, original)
        assert original in svc.pending_events(ARTIFACT)

        svc.confirm_event(ARTIFACT, original.id)
        assert original not in svc.pending_events(ARTIFACT)


# ===========================================================================
# retract_event
# ===========================================================================


class TestRetractEvent:
    def test_appends_retract_targeting_event_id(self, svc, store):
        """retract_event creates a RETRACT event whose target_ref is the original event_id."""
        original = _pending_event(type=ANSWER, actor="user")
        svc.append_event(ARTIFACT, original)

        retract = svc.retract_event(ARTIFACT, original.id)

        assert retract.type == RETRACT
        assert retract.target_ref == original.id
        assert retract.confirmed is True
        assert retract.actor == "user"

        all_events = store.get_events(ARTIFACT)
        assert retract in all_events

    def test_raises_on_nonexistent_event_id(self, svc):
        """retract_event raises ValueError when the target event doesn't exist."""
        with pytest.raises(ValueError, match="not found in artifact"):
            svc.retract_event(ARTIFACT, "no-such-event")

    def test_retract_removes_from_pending(self, svc):
        """After retracting, the event is no longer in pending_events."""
        original = _pending_event(type=ANSWER, actor="user")
        svc.append_event(ARTIFACT, original)
        assert original in svc.pending_events(ARTIFACT)

        svc.retract_event(ARTIFACT, original.id)
        assert original not in svc.pending_events(ARTIFACT)


# ===========================================================================
# batch_confirm
# ===========================================================================


class TestBatchConfirm:
    def test_confirms_multiple_events(self, svc, store):
        """batch_confirm creates one CONFIRM event per event_id."""
        e1 = _pending_event(type=EDIT, actor="system", payload={"scope": "surface"})
        e2 = _pending_event(type=EDIT, actor="system", payload={"scope": "substance"})
        e3 = _pending_event(type=CHALLENGE, actor="system")
        svc.append_event(ARTIFACT, e1)
        svc.append_event(ARTIFACT, e2)
        svc.append_event(ARTIFACT, e3)

        confirms = svc.batch_confirm(ARTIFACT, [e1.id, e2.id, e3.id])

        assert len(confirms) == 3
        target_refs = {c.target_ref for c in confirms}
        assert target_refs == {e1.id, e2.id, e3.id}
        for c in confirms:
            assert c.type == CONFIRM
            assert c.confirmed is True

    def test_batch_confirm_clears_pending(self, svc):
        """After batch_confirm, all confirmed events leave pending_events."""
        e1 = _pending_event(type=EDIT, actor="system", payload={"scope": "surface"})
        e2 = _pending_event(type=EDIT, actor="system", payload={"scope": "substance"})
        svc.append_event(ARTIFACT, e1)
        svc.append_event(ARTIFACT, e2)

        assert len(svc.pending_events(ARTIFACT)) == 2

        svc.batch_confirm(ARTIFACT, [e1.id, e2.id])

        assert len(svc.pending_events(ARTIFACT)) == 0


# ===========================================================================
# pending_events
# ===========================================================================


class TestPendingEvents:
    def test_returns_only_unconfirmed(self, svc):
        """pending_events returns only events with confirmed=False and no CONFIRM/RETRACT."""
        pending = _pending_event(type=CHALLENGE, actor="system")
        confirmed = make_event(type=ANSWER, actor="user", confirmed=True)
        svc.append_event(ARTIFACT, pending)
        svc.append_event(ARTIFACT, confirmed)

        result = svc.pending_events(ARTIFACT)
        assert pending in result
        assert confirmed not in result

    def test_empty_on_fresh_artifact(self, svc):
        """No pending events on an artifact with no events."""
        assert svc.pending_events(ARTIFACT) == []

    def test_confirm_and_retract_meta_events_excluded(self, svc):
        """CONFIRM and RETRACT meta-events themselves don't appear in pending."""
        original = _pending_event(type=CHALLENGE, actor="system")
        svc.append_event(ARTIFACT, original)
        svc.confirm_event(ARTIFACT, original.id)

        pending = svc.pending_events(ARTIFACT)
        # No CONFIRM events in pending either.
        assert all(e.type != CONFIRM for e in pending)
        assert len(pending) == 0
