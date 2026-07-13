"""Tests for anneal.services.grounding_service — literature grounding step."""

import json

import pytest

from anneal.domain.events import CHALLENGE, GROUND, PARK, make_event
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
            verdict="supports", evidence="grilling improves quality",
            assessment="Abstract directly supports the claim.",
        )

        assert event.type == GROUND
        assert event.confirmed is False
        assert event.target_ref == CLAIM_A
        assert event.payload["material_id"] == material.id
        assert event.payload["verdict"] == "supports"
        # New events write ONLY the three-state verdict — never the legacy bool.
        assert "supported" not in event.payload
        assert event.payload["evidence"] == "grilling improves quality"
        assert event.payload["assessment"] == "Abstract directly supports the claim."
        assert event.payload["source"] == "openalex"
        assert event.payload["title"] == "On the Annealing of Ideas"

        assert event in store.get_events(ARTIFACT)

    @pytest.mark.parametrize("verdict", ["supports", "contradicts", "silent"])
    def test_all_three_verdicts_accepted(self, svc, store, repo, verdict):
        """silent (查无) is a legal first-class manual judgment too."""
        _park(store)
        material = _seed_material(repo)
        event = svc.ground(ARTIFACT, CLAIM_A, material.id, verdict=verdict)
        assert event.payload["verdict"] == verdict

    def test_unknown_verdict_raises(self, svc, store, repo):
        """No boolean smuggling, no fourth state — off-enum verdicts fail."""
        _park(store)
        material = _seed_material(repo)
        with pytest.raises(ValueError, match="verdict"):
            svc.ground(ARTIFACT, CLAIM_A, material.id, verdict="not_supported")
        with pytest.raises(ValueError, match="verdict"):
            svc.ground(ARTIFACT, CLAIM_A, material.id, verdict=True)

    def test_unknown_material_raises(self, svc, store, repo):
        _park(store)
        with pytest.raises(ValueError, match="not found"):
            svc.ground(ARTIFACT, CLAIM_A, "no-such-material", verdict="supports")

    def test_unparked_artifact_raises(self, svc, repo):
        material = _seed_material(repo)
        with pytest.raises(ValueError, match="has no events"):
            svc.ground(ARTIFACT, CLAIM_A, material.id, verdict="supports")


# ===========================================================================
# auto_ground (LLM-assisted)
# ===========================================================================


class TestAutoGround:
    def _make_svc(self, store, event_svc, repo, responses):
        llm = FakeLLMClient(responses)
        return GroundingService(store, event_svc, repo=repo, llm=llm)

    def test_verdict_supports(self, store, event_svc, repo):
        _park(store)
        material = _seed_material(repo)
        svc = self._make_svc(
            store, event_svc, repo,
            [json.dumps({"verdict": "supports", "evidence": "quote", "assessment": "yes"})],
        )

        event = svc.auto_ground(ARTIFACT, CLAIM_A, "Grilling helps drafts", material.id)

        assert event.type == GROUND
        assert event.confirmed is False
        assert event.target_ref == CLAIM_A
        assert event.payload["verdict"] == "supports"
        # New events write ONLY the three-state verdict — never the legacy bool.
        assert "supported" not in event.payload
        assert event.payload["evidence"] == "quote"
        assert event.payload["assessment"] == "yes"
        assert event.payload["source"] == "openalex"
        assert event.payload["title"] == "On the Annealing of Ideas"
        assert event.payload["auto_generated"] is True
        assert event in store.get_events(ARTIFACT)

    def test_verdict_contradicts(self, store, event_svc, repo):
        _park(store)
        material = _seed_material(repo)
        svc = self._make_svc(
            store, event_svc, repo,
            [json.dumps({"verdict": "contradicts", "evidence": "null result", "assessment": "refutes"})],
        )

        event = svc.auto_ground(ARTIFACT, CLAIM_A, "Grilling helps drafts", material.id)

        assert event.payload["verdict"] == "contradicts"
        assert event.payload["auto_generated"] is True

    def test_verdict_silent(self, store, event_svc, repo):
        """查无 is a legal first-class output, not a failure."""
        _park(store)
        material = _seed_material(repo)
        svc = self._make_svc(
            store, event_svc, repo,
            [json.dumps({"verdict": "silent", "evidence": "", "assessment": "unrelated"})],
        )

        event = svc.auto_ground(ARTIFACT, CLAIM_A, "Unrelated claim", material.id)

        assert event.payload["verdict"] == "silent"
        assert event.payload["auto_generated"] is True

    def test_verdict_case_insensitive(self, store, event_svc, repo):
        """String sloppiness ('Supports') is normalized, not fatal."""
        _park(store)
        material = _seed_material(repo)
        svc = self._make_svc(
            store, event_svc, repo,
            [json.dumps({"verdict": " Supports ", "evidence": "q", "assessment": "a"})],
        )
        event = svc.auto_ground(ARTIFACT, CLAIM_A, "Some claim", material.id)
        assert event.payload["verdict"] == "supports"

    def test_without_llm_raises(self, store, event_svc, repo):
        _park(store)
        material = _seed_material(repo)
        svc = GroundingService(store, event_svc, repo=repo)  # no llm
        with pytest.raises(LLMNotConfiguredError, match="not configured"):
            svc.auto_ground(ARTIFACT, CLAIM_A, "Some claim", material.id)

    def test_missing_verdict_key_raises(self, store, event_svc, repo):
        """Fail-loud: a missing judgment is NEVER silently defaulted."""
        _park(store)
        material = _seed_material(repo)
        svc = self._make_svc(
            store, event_svc, repo,
            [json.dumps({"evidence": "quote", "assessment": "no judgment"})],
        )
        with pytest.raises(LLMResponseError, match="verdict"):
            svc.auto_ground(ARTIFACT, CLAIM_A, "Some claim", material.id)

    def test_legacy_supported_bool_from_llm_raises(self, store, event_svc, repo):
        """An LLM answering the OLD binary schema fails loud — no verdict key,
        no coercion of the legacy bool into a三态 guess."""
        _park(store)
        material = _seed_material(repo)
        svc = self._make_svc(
            store, event_svc, repo,
            [json.dumps({"supported": True, "evidence": "q", "assessment": "a"})],
        )
        with pytest.raises(LLMResponseError, match="verdict"):
            svc.auto_ground(ARTIFACT, CLAIM_A, "Some claim", material.id)

    @pytest.mark.parametrize("bad", ["maybe", "not_supported", True, 1, None])
    def test_off_enum_verdict_raises(self, store, event_svc, repo, bad):
        _park(store)
        material = _seed_material(repo)
        svc = self._make_svc(
            store, event_svc, repo,
            [json.dumps({"verdict": bad, "evidence": "q", "assessment": "a"})],
        )
        with pytest.raises(LLMResponseError, match="verdict"):
            svc.auto_ground(ARTIFACT, CLAIM_A, "Some claim", material.id)

    def test_unknown_material_raises(self, store, event_svc, repo):
        _park(store)
        svc = self._make_svc(
            store, event_svc, repo,
            [json.dumps({"verdict": "supports", "evidence": "q", "assessment": "a"})],
        )
        with pytest.raises(ValueError, match="not found"):
            svc.auto_ground(ARTIFACT, CLAIM_A, "claim", "no-such-material")

    def test_unparked_artifact_raises(self, store, event_svc, repo):
        material = _seed_material(repo)
        svc = self._make_svc(
            store, event_svc, repo,
            [json.dumps({"verdict": "supports", "evidence": "q", "assessment": "a"})],
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
            ARTIFACT, CLAIM_A, material.id, verdict="supports",
            evidence="grilling improves quality", assessment="supports",
        )
        event_svc.confirm_event(ARTIFACT, ground_event.id)

        events = store.get_events(ARTIFACT)
        feed = lens_feed_projection(events)

        ground_in_feed = [e for e in feed if e.type == GROUND]
        assert len(ground_in_feed) == 1
        assert ground_in_feed[0].id == ground_event.id
        assert ground_in_feed[0].payload["verdict"] == "supports"

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

        ground_event = svc.ground(ARTIFACT, CLAIM_A, material.id, verdict="supports")
        # Do NOT confirm.

        feed = lens_feed_projection(store.get_events(ARTIFACT))
        assert all(e.id != ground_event.id for e in feed)


# ===========================================================================
# 负证据反哺 — confirmed contradicts GROUND surfaces a pending CHALLENGE
# ===========================================================================


class TestNegativeEvidenceFeedback:
    """The soul of三态化: a signed contradicts ground lands on the board.

    The push side of the P1 对辩闭环 — enforced AT the confirm gate
    (EventService), so any confirm path (single or batch) triggers it.
    """

    def _ground_and_confirm(self, svc, event_svc, material, verdict, **kw):
        ev = svc.ground(ARTIFACT, CLAIM_A, material.id, verdict=verdict, **kw)
        event_svc.confirm_event(ARTIFACT, ev.id)
        return ev

    def _evidence_challenges(self, store):
        return [
            e
            for e in store.get_events(ARTIFACT)
            if e.type == CHALLENGE
            and e.payload.get("kind") == "evidence_contradiction"
        ]

    def test_confirmed_contradicts_surfaces_pending_challenge(
        self, svc, store, event_svc, repo
    ):
        _park(store)
        material = _seed_material(repo)
        ground_ev = self._ground_and_confirm(
            svc, event_svc, material, "contradicts",
            evidence="null result at scale", assessment="refutes",
        )

        challenges = self._evidence_challenges(store)
        assert len(challenges) == 1
        ch = challenges[0]
        # 机器起草、人签名 — same lifecycle as every system challenge.
        assert ch.actor == "system"
        assert ch.confirmed is False
        assert ch.target_ref == CLAIM_A
        # Payload carries the material reference + evidence excerpt.
        assert ch.payload["material_id"] == material.id
        assert ch.payload["title"] == "On the Annealing of Ideas"
        assert ch.payload["evidence"] == "null result at scale"
        assert ch.payload["ground_event_id"] == ground_ev.id
        assert ch.payload["auto_generated"] is True
        assert "On the Annealing of Ideas" in ch.payload["question"]
        assert "null result at scale" in ch.payload["question"]
        # It shows up on the pending (challenge-centric) board.
        pending = event_svc.pending_events(ARTIFACT)
        assert any(e.id == ch.id for e in pending)

    def test_double_confirm_is_idempotent(self, svc, store, event_svc, repo):
        _park(store)
        material = _seed_material(repo)
        ground_ev = self._ground_and_confirm(svc, event_svc, material, "contradicts")
        event_svc.confirm_event(ARTIFACT, ground_ev.id)  # confirm again

        assert len(self._evidence_challenges(store)) == 1

    @pytest.mark.parametrize("verdict", ["supports", "silent"])
    def test_non_contradicts_surfaces_nothing(
        self, svc, store, event_svc, repo, verdict
    ):
        _park(store)
        material = _seed_material(repo)
        self._ground_and_confirm(svc, event_svc, material, verdict)

        assert self._evidence_challenges(store) == []

    def test_legacy_supported_false_surfaces_nothing(
        self, store, event_svc, repo
    ):
        """Legacy `supported: False` is 未分态 — NEVER guessed into contradicts."""
        _park(store)
        material = _seed_material(repo)
        legacy = make_event(
            type=GROUND, actor="user", confirmed=False, target_ref=CLAIM_A,
            payload={"material_id": material.id, "supported": False},
        )
        event_svc.append_event(ARTIFACT, legacy)
        event_svc.confirm_event(ARTIFACT, legacy.id)

        assert [
            e
            for e in store.get_events(ARTIFACT)
            if e.type == CHALLENGE
            and e.payload.get("kind") == "evidence_contradiction"
        ] == []

    def test_retracted_challenge_stays_dismissed(
        self, svc, store, event_svc, repo
    ):
        """User retracts the surfaced challenge → re-confirming the same
        ground never resurrects it (追加否定，不删历史 — and we respect it)."""
        _park(store)
        material = _seed_material(repo)
        ground_ev = self._ground_and_confirm(svc, event_svc, material, "contradicts")
        ch = self._evidence_challenges(store)[0]
        event_svc.retract_event(ARTIFACT, ch.id)

        event_svc.confirm_event(ARTIFACT, ground_ev.id)  # confirm again

        assert len(self._evidence_challenges(store)) == 1  # still just the one
        pending = event_svc.pending_events(ARTIFACT)
        assert all(e.id != ch.id for e in pending)

    def test_no_auto_verdict_from_negative_evidence(
        self, svc, store, event_svc, repo
    ):
        """取证不定见: the反哺 produces ONLY a challenge — never a verdict."""
        from anneal.domain.events import VERDICT

        _park(store)
        material = _seed_material(repo)
        self._ground_and_confirm(svc, event_svc, material, "contradicts")

        assert [e for e in store.get_events(ARTIFACT) if e.type == VERDICT] == []
