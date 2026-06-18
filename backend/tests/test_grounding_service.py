"""Tests for anneal.services.grounding_service — literature grounding step."""

import json

import pytest

from anneal.domain.events import GROUND, PARK, make_event
from anneal.domain.models import Material
from anneal.domain.projections import lens_feed_projection
from anneal.llm.errors import LLMNotConfiguredError, LLMResponseError
from anneal.services.event_service import EventService
from anneal.services.grounding_service import GroundingService
from anneal.store.event_store import InMemoryEventStore
from anneal.store.repository import InMemoryRepository
from tests.fakes import FakeLLMClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ARTIFACT = "artifact-1"
CLAIM_A = "claim-a"


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
def svc(store, event_svc, repo):
    return GroundingService(store, event_svc, repo=repo)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _park(store, artifact_id: str = ARTIFACT, claim_id: str = CLAIM_A, kind: str = "idea"):
    event = make_event(
        type=PARK, actor="user", confirmed=True,
        target_ref=claim_id, payload={"kind": kind},
    )
    store.append(artifact_id, event)
    return event


def _seed_material(repo, library_id: str = "lib-1") -> Material:
    material = Material(
        library_id=library_id,
        kind="paper",
        provenance={"source": "openalex", "source_id": "W123", "doi": "10.1/x"},
        payload={
            "title": "On the Annealing of Ideas",
            "abstract": "We show that grilling ideas improves draft quality.",
        },
    )
    repo.create_material(material)
    return material


# ===========================================================================
# ground (manual, no LLM)
# ===========================================================================


class TestGround:
    def test_creates_pending_ground_event(self, svc, store, repo):
        _park(store)
        material = _seed_material(repo)

        event = svc.ground(
            ARTIFACT, CLAIM_A, material.id,
            supported=True, evidence="grilling improves quality",
            assessment="Abstract directly supports the claim.",
        )

        assert event.type == GROUND
        assert event.confirmed is False
        assert event.target_ref == CLAIM_A
        assert event.payload["material_id"] == material.id
        assert event.payload["supported"] is True
        assert event.payload["evidence"] == "grilling improves quality"
        assert event.payload["assessment"] == "Abstract directly supports the claim."
        assert event.payload["source"] == "openalex"
        assert event.payload["title"] == "On the Annealing of Ideas"

        assert event in store.get_events(ARTIFACT)

    def test_unknown_material_raises(self, svc, store, repo):
        _park(store)
        with pytest.raises(ValueError, match="not found"):
            svc.ground(ARTIFACT, CLAIM_A, "no-such-material", supported=True)

    def test_unparked_artifact_raises(self, svc, repo):
        material = _seed_material(repo)
        with pytest.raises(ValueError, match="has no events"):
            svc.ground(ARTIFACT, CLAIM_A, material.id, supported=True)


# ===========================================================================
# auto_ground (LLM-assisted)
# ===========================================================================


class TestAutoGround:
    def _make_svc(self, store, event_svc, repo, responses):
        llm = FakeLLMClient(responses)
        return GroundingService(store, event_svc, repo=repo, llm=llm)

    def test_supported_true(self, store, event_svc, repo):
        _park(store)
        material = _seed_material(repo)
        svc = self._make_svc(
            store, event_svc, repo,
            [json.dumps({"supported": True, "evidence": "quote", "assessment": "yes"})],
        )

        event = svc.auto_ground(ARTIFACT, CLAIM_A, "Grilling helps drafts", material.id)

        assert event.type == GROUND
        assert event.confirmed is False
        assert event.target_ref == CLAIM_A
        assert event.payload["supported"] is True
        assert event.payload["evidence"] == "quote"
        assert event.payload["assessment"] == "yes"
        assert event.payload["source"] == "openalex"
        assert event.payload["title"] == "On the Annealing of Ideas"
        assert event.payload["auto_generated"] is True
        assert event in store.get_events(ARTIFACT)

    def test_supported_false(self, store, event_svc, repo):
        _park(store)
        material = _seed_material(repo)
        svc = self._make_svc(
            store, event_svc, repo,
            [json.dumps({"supported": False, "evidence": "", "assessment": "unrelated"})],
        )

        event = svc.auto_ground(ARTIFACT, CLAIM_A, "Unrelated claim", material.id)

        assert event.payload["supported"] is False
        assert event.payload["auto_generated"] is True

    def test_without_llm_raises(self, store, event_svc, repo):
        _park(store)
        material = _seed_material(repo)
        svc = GroundingService(store, event_svc, repo=repo)  # no llm
        with pytest.raises(LLMNotConfiguredError, match="not configured"):
            svc.auto_ground(ARTIFACT, CLAIM_A, "Some claim", material.id)

    def test_missing_supported_key_raises(self, store, event_svc, repo):
        _park(store)
        material = _seed_material(repo)
        svc = self._make_svc(
            store, event_svc, repo,
            [json.dumps({"evidence": "quote", "assessment": "no judgment"})],
        )
        with pytest.raises(LLMResponseError, match="supported"):
            svc.auto_ground(ARTIFACT, CLAIM_A, "Some claim", material.id)

    def test_unknown_material_raises(self, store, event_svc, repo):
        _park(store)
        svc = self._make_svc(
            store, event_svc, repo,
            [json.dumps({"supported": True, "evidence": "q", "assessment": "a"})],
        )
        with pytest.raises(ValueError, match="not found"):
            svc.auto_ground(ARTIFACT, CLAIM_A, "claim", "no-such-material")

    def test_unparked_artifact_raises(self, store, event_svc, repo):
        material = _seed_material(repo)
        svc = self._make_svc(
            store, event_svc, repo,
            [json.dumps({"supported": True, "evidence": "q", "assessment": "a"})],
        )
        with pytest.raises(ValueError, match="has no events"):
            svc.auto_ground(ARTIFACT, CLAIM_A, "claim", material.id)


# ===========================================================================
# Projection: confirmed GROUND feeds the Lens
# ===========================================================================


class TestGroundFeedsLens:
    def test_confirmed_ground_in_lens_feed(self, store, event_svc, repo):
        """On a grilled artifact, a confirmed GROUND event feeds the Lens.

        lens_feed_projection requires the artifact to have grill events;
        we add a confirmed CHALLENGE so the feed is non-empty, then ground
        and confirm — the ground event must appear in the feed.
        """
        from anneal.domain.events import CHALLENGE

        _park(store)
        material = _seed_material(repo)
        svc = GroundingService(store, event_svc, repo=repo)

        # Make the artifact "grilled" so lens_feed is active.
        challenge = make_event(
            type=CHALLENGE, actor="system", confirmed=False, target_ref=CLAIM_A,
            payload={"question": "Why?"},
        )
        event_svc.append_event(ARTIFACT, challenge)
        event_svc.confirm_event(ARTIFACT, challenge.id)

        ground_event = svc.ground(
            ARTIFACT, CLAIM_A, material.id, supported=True,
            evidence="grilling improves quality", assessment="supports",
        )
        event_svc.confirm_event(ARTIFACT, ground_event.id)

        events = store.get_events(ARTIFACT)
        feed = lens_feed_projection(events)

        ground_in_feed = [e for e in feed if e.type == GROUND]
        assert len(ground_in_feed) == 1
        assert ground_in_feed[0].id == ground_event.id
        assert ground_in_feed[0].payload["supported"] is True

    def test_pending_ground_not_in_lens_feed(self, store, event_svc, repo):
        """An unconfirmed GROUND event does NOT feed the Lens (Fix 5)."""
        from anneal.domain.events import CHALLENGE

        _park(store)
        material = _seed_material(repo)
        svc = GroundingService(store, event_svc, repo=repo)

        challenge = make_event(
            type=CHALLENGE, actor="system", confirmed=False, target_ref=CLAIM_A,
            payload={"question": "Why?"},
        )
        event_svc.append_event(ARTIFACT, challenge)
        event_svc.confirm_event(ARTIFACT, challenge.id)

        ground_event = svc.ground(ARTIFACT, CLAIM_A, material.id, supported=True)
        # Do NOT confirm.

        feed = lens_feed_projection(store.get_events(ARTIFACT))
        assert all(e.id != ground_event.id for e in feed)
