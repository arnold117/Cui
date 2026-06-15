"""Tests for anneal.services.park_service — sealed isolation zone."""

import pytest

from anneal.domain.events import (
    ANSWER,
    CHALLENGE,
    PARK,
    VERDICT,
    Event,
    make_event,
)
from anneal.domain.projections import is_parked, lens_feed_projection
from anneal.services.event_service import EventService
from anneal.services.park_service import ParkService
from anneal.store.event_store import InMemoryEventStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

LIBRARY = "lib-1"


@pytest.fixture
def store():
    return InMemoryEventStore()


@pytest.fixture
def event_service(store):
    return EventService(store)


@pytest.fixture
def svc(store, event_service):
    return ParkService(store, event_service)


# ===========================================================================
# park — happy path
# ===========================================================================


class TestPark:
    def test_creates_artifact_and_claim(self, svc):
        """park returns an Artifact and Claim with correct fields."""
        artifact, claim = svc.park(LIBRARY, "some inspiration")

        assert artifact.library_id == LIBRARY
        assert artifact.kind == "idea"
        assert artifact.goal == "some inspiration"

        assert claim.library_id == LIBRARY
        assert claim.body == "some inspiration"
        assert artifact.id in claim.artifact_ids

    def test_appends_park_event(self, svc, store):
        """park appends a PARK event with confirmed=True, debt=False, target_ref=claim.id."""
        artifact, claim = svc.park(LIBRARY, "test idea")

        events = store.get_events(artifact.id)
        assert len(events) == 1

        evt = events[0]
        assert evt.type == PARK
        assert evt.confirmed is True
        assert evt.debt is False
        assert evt.target_ref == claim.id
        assert evt.actor == "user"

    def test_kind_idea_succeeds(self, svc):
        """kind='idea' is in SUPPORTED_KINDS and works."""
        artifact, claim = svc.park(LIBRARY, "idea body", kind="idea")
        assert artifact.kind == "idea"

    def test_kind_review_succeeds(self, svc):
        """kind='review' is in SUPPORTED_KINDS and works."""
        artifact, claim = svc.park(LIBRARY, "review body", kind="review")
        assert artifact.kind == "review"


# ===========================================================================
# park — kind validation (service-layer, not model)
# ===========================================================================


class TestParkKindValidation:
    def test_paper_raises(self, svc):
        """kind='paper' is not supported in first cut."""
        with pytest.raises(ValueError, match="Unsupported artifact kind"):
            svc.park(LIBRARY, "paper body", kind="paper")

    def test_revision_raises(self, svc):
        """kind='revision' is not supported in first cut."""
        with pytest.raises(ValueError, match="Unsupported artifact kind"):
            svc.park(LIBRARY, "revision body", kind="revision")


# ===========================================================================
# is_parked projection on parked artifact
# ===========================================================================


class TestIsParkedProjection:
    def test_parked_artifact_is_parked(self, svc, store):
        """An artifact with only a park event is identified as parked."""
        artifact, _ = svc.park(LIBRARY, "still parked")
        events = store.get_events(artifact.id)
        assert is_parked(events) is True

    def test_parked_artifact_lens_feed_empty(self, svc, store):
        """Park isolation: lens_feed_projection returns empty for a parked-only artifact."""
        artifact, _ = svc.park(LIBRARY, "isolated idea")
        events = store.get_events(artifact.id)
        assert lens_feed_projection(events) == []


# ===========================================================================
# list_parked
# ===========================================================================


class TestListParked:
    def test_identifies_parked_vs_grilled(self, svc, store):
        """list_parked correctly separates parked artifacts from grilled ones."""
        # Park two artifacts
        a1, _ = svc.park(LIBRARY, "idea one")
        a2, _ = svc.park(LIBRARY, "idea two")

        # Simulate grilling artifact a2 by adding grill events
        challenge = make_event(
            type=CHALLENGE, actor="system", confirmed=True, payload={"question": "why?"}
        )
        answer = make_event(
            type=ANSWER, actor="user", confirmed=True, payload={"response": "because"}
        )
        verdict = make_event(
            type=VERDICT,
            actor="system",
            confirmed=True,
            target_ref="claim-x",
            payload={"outcome": "survive"},
        )
        store.append(a2.id, challenge)
        store.append(a2.id, answer)
        store.append(a2.id, verdict)

        # Build the artifacts_with_events list
        artifacts_with_events = [
            (a1.id, store.get_events(a1.id)),
            (a2.id, store.get_events(a2.id)),
        ]

        parked_ids = svc.list_parked(LIBRARY, artifacts_with_events)

        # a1 is still parked (only park event)
        assert a1.id in parked_ids
        # a2 has been grilled — no longer parked
        assert a2.id not in parked_ids

    def test_empty_when_all_grilled(self, svc, store):
        """list_parked returns empty when all artifacts have been grilled."""
        a1, _ = svc.park(LIBRARY, "to be grilled")

        # Grill it
        challenge = make_event(
            type=CHALLENGE, actor="system", confirmed=True, payload={"question": "why?"}
        )
        store.append(a1.id, challenge)

        artifacts_with_events = [
            (a1.id, store.get_events(a1.id)),
        ]

        assert svc.list_parked(LIBRARY, artifacts_with_events) == []

    def test_all_parked(self, svc, store):
        """list_parked returns all artifact_ids when none are grilled."""
        a1, _ = svc.park(LIBRARY, "one")
        a2, _ = svc.park(LIBRARY, "two")

        artifacts_with_events = [
            (a1.id, store.get_events(a1.id)),
            (a2.id, store.get_events(a2.id)),
        ]

        parked_ids = svc.list_parked(LIBRARY, artifacts_with_events)
        assert set(parked_ids) == {a1.id, a2.id}


# ===========================================================================
# get_events
# ===========================================================================


class TestGetEvents:
    def test_returns_events_for_artifact(self, svc, store):
        """get_events returns all events stored for an artifact."""
        artifact, _ = svc.park(LIBRARY, "tracked idea")
        events = svc.get_events(artifact.id)
        assert len(events) == 1
        assert events[0].type == PARK
