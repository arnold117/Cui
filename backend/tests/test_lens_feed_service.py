"""Tests for anneal.services.lens_feed_service — Lens feed ingestion.

Spec §5 line 5: "这条完整 trajectory 能被写入 Lens 投喂点
（哪怕下游只是落库、不学习）。"

Uses ParkService + GrillService + EventService to set up realistic
test fixtures (real service interactions, not hand-rolled events).
"""

import pytest

from anneal.domain.events import (
    ANSWER,
    CHALLENGE,
    EDIT,
    VERDICT,
    make_event,
)
from anneal.domain.invariants import ParkIsolationViolation
from anneal.services.event_service import EventService
from anneal.services.grill_service import GrillService
from anneal.services.lens_feed_service import (
    InMemoryLensFeedStore,
    LensFeedService,
)
from anneal.services.park_service import ParkService
from anneal.store.event_store import InMemoryEventStore
from anneal.store.repository import InMemoryRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

LIBRARY = "lib-1"
LIBRARY_OTHER = "lib-other"


@pytest.fixture
def store():
    return InMemoryEventStore()


@pytest.fixture
def event_svc(store):
    return EventService(store)


@pytest.fixture
def repo():
    return InMemoryRepository()


@pytest.fixture
def park_svc(store, event_svc, repo):
    return ParkService(store, event_svc, repo=repo)


@pytest.fixture
def grill_svc(store, event_svc):
    return GrillService(store, event_svc)


@pytest.fixture
def feed_store():
    return InMemoryLensFeedStore()


@pytest.fixture
def svc(store, feed_store):
    return LensFeedService(event_store=store, feed_store=feed_store)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _full_grill_survive(park_svc, grill_svc, event_svc, store, library_id=LIBRARY):
    """Park -> grill -> challenge -> answer -> verdict(survive), all confirmed.

    Returns (artifact, claim) tuple.
    """
    artifact, claim = park_svc.park(library_id, "Test hypothesis")
    grill_svc.start_grill(artifact.id, kind=artifact.kind)

    challenge = grill_svc.challenge(artifact.id, claim.id, "What evidence?")
    answer = grill_svc.answer(artifact.id, claim.id, "Study X shows Y")
    verdict = grill_svc.verdict(artifact.id, claim.id, "survive", "Evidence is solid")

    # Confirm system events.
    event_svc.confirm_event(artifact.id, challenge.id)
    event_svc.confirm_event(artifact.id, verdict.id)

    return artifact, claim


def _full_grill_kill(park_svc, grill_svc, event_svc, store, library_id=LIBRARY):
    """Park -> grill -> challenge -> answer -> verdict(kill), all confirmed.

    Returns (artifact, claim) tuple.
    """
    artifact, claim = park_svc.park(library_id, "Weak hypothesis")
    grill_svc.start_grill(artifact.id, kind=artifact.kind)

    challenge = grill_svc.challenge(artifact.id, claim.id, "Can you prove this?")
    answer = grill_svc.answer(artifact.id, claim.id, "I cannot find evidence")
    verdict = grill_svc.verdict(artifact.id, claim.id, "kill", "Claim unsupported", death_cause="refuted")

    # Confirm system events.
    event_svc.confirm_event(artifact.id, challenge.id)
    event_svc.confirm_event(artifact.id, verdict.id)

    return artifact, claim


# ===========================================================================
# ingest — happy path: fully grilled trajectory
# ===========================================================================


class TestIngestGrilledTrajectory:
    def test_ingest_fully_grilled_trajectory(
        self, svc, park_svc, grill_svc, event_svc, store
    ):
        """Ingest a fully grilled trajectory -- entries appear in feed."""
        artifact, claim = _full_grill_survive(
            park_svc, grill_svc, event_svc, store
        )

        entries = svc.ingest(artifact.id, LIBRARY)

        # Should have entries for the grilled events
        # (challenge confirmed, answer confirmed, verdict confirmed).
        assert len(entries) > 0

        # All entries should have correct library_id and artifact_id.
        for entry in entries:
            assert entry.library_id == LIBRARY
            assert entry.artifact_id == artifact.id
            assert entry.event_id  # non-empty
            assert entry.event_type  # non-empty

    def test_ingested_entries_have_correct_fields(
        self, svc, park_svc, grill_svc, event_svc, store
    ):
        """Ingested entries have correct artifact_id, event_id, event_type."""
        artifact, claim = _full_grill_survive(
            park_svc, grill_svc, event_svc, store
        )

        entries = svc.ingest(artifact.id, LIBRARY)

        # Collect event types that should appear.
        event_types_in_feed = {e.event_type for e in entries}
        # A survived trajectory includes challenge, answer, verdict.
        assert CHALLENGE in event_types_in_feed
        assert ANSWER in event_types_in_feed
        assert VERDICT in event_types_in_feed

        # Each entry's event_id should be a real event in the store.
        all_event_ids = {e.id for e in store.get_events(artifact.id)}
        for entry in entries:
            assert entry.event_id in all_event_ids


# ===========================================================================
# ingest — killed ideas are included (spec §2.2)
# ===========================================================================


class TestIngestKilledIdeas:
    def test_feed_includes_killed_ideas(
        self, svc, park_svc, grill_svc, event_svc, store
    ):
        """Feed includes killed ideas -- they are mining material (spec §2.2)."""
        artifact, claim = _full_grill_kill(
            park_svc, grill_svc, event_svc, store
        )

        entries = svc.ingest(artifact.id, LIBRARY)

        # Should have entries -- killed ideas are Lens food.
        assert len(entries) > 0

        # The kill verdict should be in the feed.
        kill_entries = [
            e for e in entries if e.event_type == VERDICT
        ]
        assert len(kill_entries) >= 1


# ===========================================================================
# ingest — PARK isolation: parked-only items raise
# ===========================================================================


class TestIngestParkIsolation:
    def test_feed_excludes_park_only_items(
        self, svc, park_svc
    ):
        """Feed excludes PARK-only items -- assert_park_isolation raises."""
        artifact, _claim = park_svc.park(LIBRARY, "Still in park")

        with pytest.raises(ParkIsolationViolation, match="PARK isolation"):
            svc.ingest(artifact.id, LIBRARY)


# ===========================================================================
# ingest — surface-scope edits excluded
# ===========================================================================


class TestIngestSurfaceEditsExcluded:
    def test_feed_excludes_surface_scope_edits(
        self, svc, park_svc, grill_svc, event_svc, store
    ):
        """Feed excludes surface-scope edits (spec §2.6 decision 4)."""
        artifact, claim = _full_grill_survive(
            park_svc, grill_svc, event_svc, store
        )

        # Add a surface-scope edit (confirmed).
        surface_edit = make_event(
            type=EDIT,
            actor="user",
            confirmed=True,
            payload={"scope": "surface", "content": "typo fix"},
        )
        store.append(artifact.id, surface_edit)

        # Add a substance-scope edit (confirmed) for contrast.
        substance_edit = make_event(
            type=EDIT,
            actor="user",
            confirmed=True,
            payload={"scope": "substance", "content": "restructured argument"},
        )
        store.append(artifact.id, substance_edit)

        entries = svc.ingest(artifact.id, LIBRARY)

        event_ids_in_feed = {e.event_id for e in entries}

        # Surface edit should NOT be in the feed.
        assert surface_edit.id not in event_ids_in_feed

        # Substance edit SHOULD be in the feed.
        assert substance_edit.id in event_ids_in_feed


# ===========================================================================
# ingest — unconfirmed events excluded
# ===========================================================================


class TestIngestUnconfirmedExcluded:
    def test_feed_excludes_unconfirmed_events(
        self, svc, park_svc, grill_svc, event_svc, store
    ):
        """Feed excludes unconfirmed events."""
        artifact, claim = park_svc.park(LIBRARY, "Test hypothesis")
        grill_svc.start_grill(artifact.id, kind=artifact.kind)

        # Add grill events but do NOT confirm the system ones.
        challenge = grill_svc.challenge(artifact.id, claim.id, "What evidence?")
        answer = grill_svc.answer(artifact.id, claim.id, "Study X")
        verdict = grill_svc.verdict(artifact.id, claim.id, "survive", "OK")

        # Only confirm the challenge, leave verdict unconfirmed.
        event_svc.confirm_event(artifact.id, challenge.id)

        entries = svc.ingest(artifact.id, LIBRARY)

        event_ids_in_feed = {e.event_id for e in entries}

        # Challenge is confirmed -> should be in feed.
        assert challenge.id in event_ids_in_feed

        # Answer is confirmed=True (user action) -> should be in feed.
        assert answer.id in event_ids_in_feed

        # Verdict is NOT confirmed -> should NOT be in feed.
        assert verdict.id not in event_ids_in_feed


# ===========================================================================
# query_feed — scoped to library_id
# ===========================================================================


class TestQueryFeed:
    def test_query_feed_returns_entries_scoped_to_library(
        self, svc, park_svc, grill_svc, event_svc, store
    ):
        """query_feed returns entries scoped to library_id."""
        # Ingest into LIBRARY.
        artifact, claim = _full_grill_survive(
            park_svc, grill_svc, event_svc, store, library_id=LIBRARY
        )
        svc.ingest(artifact.id, LIBRARY)

        # Ingest into LIBRARY_OTHER.
        artifact_other, claim_other = _full_grill_survive(
            park_svc, grill_svc, event_svc, store, library_id=LIBRARY_OTHER
        )
        svc.ingest(artifact_other.id, LIBRARY_OTHER)

        # Query LIBRARY -- should only see LIBRARY entries.
        lib_entries = svc.query_feed(LIBRARY)
        assert len(lib_entries) > 0
        assert all(e.library_id == LIBRARY for e in lib_entries)

        # Query LIBRARY_OTHER -- should only see LIBRARY_OTHER entries.
        other_entries = svc.query_feed(LIBRARY_OTHER)
        assert len(other_entries) > 0
        assert all(e.library_id == LIBRARY_OTHER for e in other_entries)

    def test_query_feed_returns_nothing_for_empty_library(self, svc):
        """query_feed returns nothing for a library with no ingested trajectories."""
        entries = svc.query_feed("lib-nonexistent")
        assert entries == []

    def test_query_feed_returns_nothing_for_parked_only(
        self, svc, park_svc
    ):
        """query_feed returns nothing when only parked items exist (never ingested)."""
        park_svc.park(LIBRARY, "Just parked, never grilled")

        # Never called ingest, so query should be empty.
        entries = svc.query_feed(LIBRARY)
        assert entries == []
