"""Tests for anneal.services.grill_service — adversarial questioning loop."""

import json

import pytest

from anneal.domain.events import (
    ANSWER,
    CHALLENGE,
    CONFIRM,
    PARK,
    VERDICT,
    make_event,
)
from anneal.domain.projections import claim_status, lens_feed_projection
from anneal.llm.errors import LLMNotConfiguredError, LLMResponseError
from anneal.services.event_service import EventService
from anneal.services.grill_service import GrillService
from anneal.services.park_service import ParkService
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
def svc(store, event_svc):
    return GrillService(store, event_svc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _park(store, artifact_id: str = ARTIFACT, claim_id: str = "claim-test", kind: str = "idea"):
    """Put a park event into the store for the given artifact."""
    event = make_event(
        type=PARK, actor="user", confirmed=True,
        target_ref=claim_id, payload={"kind": kind},
    )
    store.append(artifact_id, event)
    return event


# ===========================================================================
# start_grill — validation gate
# ===========================================================================


class TestStartGrill:
    def test_validates_artifact_is_parked(self, svc, store):
        """start_grill succeeds when artifact has a park event."""
        _park(store)
        # Should not raise.
        svc.start_grill(ARTIFACT, kind="idea")

    def test_raises_on_non_parked_artifact(self, svc):
        """start_grill raises ValueError when artifact has no events."""
        with pytest.raises(ValueError, match="no events"):
            svc.start_grill(ARTIFACT, kind="idea")

    def test_raises_on_already_grilled_artifact(self, svc, store, event_svc):
        """start_grill raises ValueError when artifact already has grill events."""
        _park(store)
        # Add a challenge event to simulate grilling already started.
        challenge = make_event(
            type=CHALLENGE, actor="system", confirmed=False, target_ref=CLAIM_A,
        )
        event_svc.append_event(ARTIFACT, challenge)

        with pytest.raises(ValueError, match="already has grill events"):
            svc.start_grill(ARTIFACT, kind="idea")

    def test_raises_on_unsupported_kind(self, svc, store):
        """start_grill raises ValueError for unsupported artifact kind."""
        _park(store)
        with pytest.raises(ValueError, match="Unsupported artifact kind"):
            svc.start_grill(ARTIFACT, kind="paper")

    def test_kind_idea_succeeds(self, svc, store):
        """kind='idea' is supported."""
        _park(store)
        svc.start_grill(ARTIFACT, kind="idea")

    def test_kind_review_succeeds(self, svc, store):
        """kind='review' is supported — same flow as idea."""
        _park(store)
        svc.start_grill(ARTIFACT, kind="review")


# ===========================================================================
# challenge
# ===========================================================================


class TestChallenge:
    def test_appends_challenge_event(self, svc, store):
        """challenge() creates a CHALLENGE event in the store."""
        _park(store)
        event = svc.challenge(ARTIFACT, CLAIM_A, "Why is this true?")

        assert event.type == CHALLENGE
        assert event.actor == "system"
        assert event.target_ref == CLAIM_A
        assert event.payload["question"] == "Why is this true?"

        all_events = store.get_events(ARTIFACT)
        assert event in all_events

    def test_challenge_confirmed_false(self, svc, store):
        """System-generated challenge has confirmed=False (spec §2.6 decision #2)."""
        _park(store)
        event = svc.challenge(ARTIFACT, CLAIM_A, "Prove it")
        assert event.confirmed is False

    def test_challenge_on_empty_artifact_raises(self, svc):
        """challenge() on artifact with no events raises ValueError."""
        with pytest.raises(ValueError, match="has no events"):
            svc.challenge(ARTIFACT, CLAIM_A, "Why?")

    def test_challenge_on_unparked_artifact_raises(self, svc, store, event_svc):
        """challenge() on artifact that was never parked raises ValueError."""
        # Manually insert a non-park event so artifact exists but was never parked.
        event = make_event(type=ANSWER, actor="user", confirmed=True, target_ref=CLAIM_A)
        event_svc.append_event(ARTIFACT, event)
        with pytest.raises(ValueError, match="was never parked"):
            svc.challenge(ARTIFACT, CLAIM_A, "Why?")

    def test_challenge_on_parked_artifact_succeeds(self, svc, store):
        """challenge() on parked-only artifact succeeds (first grill entry)."""
        _park(store)
        event = svc.challenge(ARTIFACT, CLAIM_A, "Why?")
        assert event.type == CHALLENGE

    def test_challenge_on_already_grilling_artifact_succeeds(self, svc, store):
        """challenge() on artifact already in grill (has challenge) succeeds."""
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "First question")
        event = svc.challenge(ARTIFACT, CLAIM_A, "Second question")
        assert event.type == CHALLENGE


# ===========================================================================
# answer
# ===========================================================================


class TestAnswer:
    def test_appends_answer_event(self, svc, store):
        """answer() creates an ANSWER event in the store."""
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")
        event = svc.answer(ARTIFACT, CLAIM_A, "Because X, Y, Z")

        assert event.type == ANSWER
        assert event.actor == "user"
        assert event.target_ref == CLAIM_A
        assert event.payload["response"] == "Because X, Y, Z"

        all_events = store.get_events(ARTIFACT)
        assert event in all_events

    def test_answer_confirmed_true(self, svc, store):
        """User action answer has confirmed=True — user doing it IS confirmation."""
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Prove it")
        event = svc.answer(ARTIFACT, CLAIM_A, "Here is my evidence")
        assert event.confirmed is True

    def test_answer_on_parked_only_raises(self, svc, store):
        """answer() on parked-only artifact (no challenge) raises ValueError."""
        _park(store)
        with pytest.raises(ValueError, match="No challenge exists"):
            svc.answer(ARTIFACT, CLAIM_A, "response")

    def test_answer_after_challenge_succeeds(self, svc, store):
        """answer() after challenge succeeds."""
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")
        event = svc.answer(ARTIFACT, CLAIM_A, "Because reasons")
        assert event.type == ANSWER

    def test_answer_records_challenge_id_when_provided(self, svc, store):
        """answer(challenge_id=...) records it in the ANSWER payload."""
        _park(store)
        challenge = svc.challenge(ARTIFACT, CLAIM_A, "Why?")
        event = svc.answer(ARTIFACT, CLAIM_A, "Because X", challenge_id=challenge.id)
        assert event.payload["challenge_id"] == challenge.id

    def test_answer_omits_challenge_id_when_not_provided(self, svc, store):
        """Without challenge_id, the ANSWER payload carries no challenge_id key."""
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")
        event = svc.answer(ARTIFACT, CLAIM_A, "Because X")
        assert "challenge_id" not in event.payload


# ===========================================================================
# verdict
# ===========================================================================


class TestVerdict:
    def test_appends_verdict_survive(self, svc, store):
        """verdict(outcome='survive') creates a VERDICT event."""
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")
        event = svc.verdict(ARTIFACT, CLAIM_A, "survive", "Evidence checks out")

        assert event.type == VERDICT
        assert event.actor == "system"
        assert event.target_ref == CLAIM_A
        assert event.payload["outcome"] == "survive"
        assert event.payload["rationale"] == "Evidence checks out"

    def test_appends_verdict_kill(self, svc, store):
        """verdict(outcome='kill') creates a VERDICT event."""
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")
        event = svc.verdict(ARTIFACT, CLAIM_A, "kill", "No supporting evidence", death_cause="refuted")

        assert event.type == VERDICT
        assert event.payload["outcome"] == "kill"

    def test_verdict_confirmed_false(self, svc, store):
        """System judgment verdict has confirmed=False (needs user confirmation)."""
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")
        event = svc.verdict(ARTIFACT, CLAIM_A, "survive", "OK")
        assert event.confirmed is False

    def test_invalid_outcome_raises(self, svc, store):
        """Verdict outcome must be 'survive' or 'kill' — anything else raises ValueError."""
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")
        with pytest.raises(ValueError, match="must be 'survive' or 'kill'"):
            svc.verdict(ARTIFACT, CLAIM_A, "maybe", "unsure")

    def test_invalid_outcome_pass_raises(self, svc, store):
        """'pass' is not a valid outcome."""
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")
        with pytest.raises(ValueError, match="must be 'survive' or 'kill'"):
            svc.verdict(ARTIFACT, CLAIM_A, "pass", "let it through")

    def test_verdict_on_parked_only_raises(self, svc, store):
        """verdict() on parked-only artifact (no challenge) raises ValueError."""
        _park(store)
        with pytest.raises(ValueError, match="No challenge exists"):
            svc.verdict(ARTIFACT, CLAIM_A, "survive", "OK")

    def test_verdict_records_challenge_id_when_provided(self, svc, store):
        """verdict(challenge_id=...) records it in the VERDICT payload."""
        _park(store)
        challenge = svc.challenge(ARTIFACT, CLAIM_A, "Why?")
        event = svc.verdict(
            ARTIFACT, CLAIM_A, "survive", "OK", challenge_id=challenge.id
        )
        assert event.payload["challenge_id"] == challenge.id

    def test_verdict_omits_challenge_id_when_not_provided(self, svc, store):
        """Without challenge_id, the VERDICT payload carries no challenge_id key."""
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")
        event = svc.verdict(ARTIFACT, CLAIM_A, "survive", "OK")
        assert "challenge_id" not in event.payload


# ===========================================================================
# bypass
# ===========================================================================


class TestBypass:
    def test_creates_verdict_with_debt(self, svc, store):
        """bypass() creates a VERDICT event with debt=True."""
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")
        event = svc.bypass(ARTIFACT, CLAIM_A)

        assert event.type == VERDICT
        assert event.payload["outcome"] == "survive"
        assert event.debt is True
        assert event.target_ref == CLAIM_A

    def test_bypass_confirmed_false(self, svc, store):
        """Bypass verdict has confirmed=False (needs user confirmation)."""
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")
        event = svc.bypass(ARTIFACT, CLAIM_A)
        assert event.confirmed is False

    def test_bypass_then_confirm_clears_debt(self, svc, store, event_svc):
        """After bypass + confirm, the debt is resolved.

        A CONFIRM event targeting the bypass verdict's id clears the debt.
        """
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")
        bypass_event = svc.bypass(ARTIFACT, CLAIM_A)
        assert bypass_event.debt is True

        # Confirm the bypass verdict to clear debt.
        confirm = event_svc.confirm_event(ARTIFACT, bypass_event.id)
        assert confirm.type == CONFIRM
        assert confirm.target_ref == bypass_event.id

        # Verify debt is resolved — no pending events for the bypass.
        pending = event_svc.pending_events(ARTIFACT)
        assert bypass_event not in pending

    def test_bypass_on_parked_only_raises(self, svc, store):
        """bypass() on parked-only artifact (no challenge) raises ValueError."""
        _park(store)
        with pytest.raises(ValueError, match="No challenge exists"):
            svc.bypass(ARTIFACT, CLAIM_A)


# ===========================================================================
# Full cycles
# ===========================================================================


class TestFullCycleSurvive:
    def test_park_grill_challenge_answer_verdict_survive(self, svc, store, event_svc):
        """Full cycle: park -> start_grill -> challenge -> answer -> verdict(survive).

        After confirming the verdict, claim_status returns 'survived'.
        """
        _park(store)
        svc.start_grill(ARTIFACT, kind="idea")

        challenge = svc.challenge(ARTIFACT, CLAIM_A, "What evidence do you have?")
        answer = svc.answer(ARTIFACT, CLAIM_A, "Study X shows Y")
        verdict = svc.verdict(ARTIFACT, CLAIM_A, "survive", "Evidence is solid")

        # Confirm system events (challenge and verdict).
        event_svc.confirm_event(ARTIFACT, challenge.id)
        event_svc.confirm_event(ARTIFACT, verdict.id)

        events = store.get_events(ARTIFACT)
        status = claim_status(events, CLAIM_A)
        assert status == "survived"


class TestFullCycleKill:
    def test_park_grill_challenge_answer_verdict_kill(self, svc, store, event_svc):
        """Full cycle with kill: verdict(kill) — killed event persists in trajectory.

        claim_status returns 'killed'.
        """
        _park(store)
        svc.start_grill(ARTIFACT, kind="idea")

        challenge = svc.challenge(ARTIFACT, CLAIM_A, "Can you prove this?")
        answer = svc.answer(ARTIFACT, CLAIM_A, "I cannot find evidence")
        verdict = svc.verdict(ARTIFACT, CLAIM_A, "kill", "Claim unsupported", death_cause="refuted")

        # Confirm system events.
        event_svc.confirm_event(ARTIFACT, challenge.id)
        event_svc.confirm_event(ARTIFACT, verdict.id)

        events = store.get_events(ARTIFACT)
        status = claim_status(events, CLAIM_A)
        assert status == "killed"

        # Killed event persists in trajectory — it's still in the event stream.
        verdicts = store.get_events_by_type(ARTIFACT, VERDICT)
        assert any(
            v.payload.get("outcome") == "kill" and v.target_ref == CLAIM_A
            for v in verdicts
        )

    def test_killed_idea_appears_in_lens_feed(self, svc, store, event_svc):
        """Killed idea appears in lens_feed_projection — it's mining material.

        Spec §2.2: killed ideas are private assets, not garbage.
        """
        _park(store)
        svc.start_grill(ARTIFACT, kind="idea")

        challenge = svc.challenge(ARTIFACT, CLAIM_A, "Prove it")
        answer = svc.answer(ARTIFACT, CLAIM_A, "Cannot")
        verdict = svc.verdict(ARTIFACT, CLAIM_A, "kill", "No evidence", death_cause="refuted")

        # Confirm system events so they appear in lens feed.
        event_svc.confirm_event(ARTIFACT, challenge.id)
        event_svc.confirm_event(ARTIFACT, verdict.id)

        events = store.get_events(ARTIFACT)
        feed = lens_feed_projection(events)

        # The kill verdict should be in the lens feed.
        kill_verdicts = [
            e for e in feed
            if e.type == VERDICT and e.payload.get("outcome") == "kill"
        ]
        assert len(kill_verdicts) >= 1
        assert kill_verdicts[0].target_ref == CLAIM_A


class TestUnifiedSchema:
    def test_idea_and_review_use_same_flow(self, svc, store, event_svc):
        """Both kind='idea' and kind='review' work with the same grill flow.

        Spec §5.6: both flows use the same trajectory schema (unified verbs).
        """
        # --- Idea artifact ---
        idea_artifact = "artifact-idea"
        idea_claim = "claim-idea"
        park_idea = make_event(type=PARK, actor="user", confirmed=True)
        store.append(idea_artifact, park_idea)
        svc.start_grill(idea_artifact, kind="idea")
        svc.challenge(idea_artifact, idea_claim, "Why?")
        svc.answer(idea_artifact, idea_claim, "Because")
        svc.verdict(idea_artifact, idea_claim, "survive", "OK")

        # --- Review artifact ---
        review_artifact = "artifact-review"
        review_claim = "claim-review"
        park_review = make_event(type=PARK, actor="user", confirmed=True)
        store.append(review_artifact, park_review)
        svc.start_grill(review_artifact, kind="review")
        svc.challenge(review_artifact, review_claim, "Justify this critique")
        svc.answer(review_artifact, review_claim, "Evidence from paper X")
        svc.verdict(review_artifact, review_claim, "survive", "Solid critique")

        # Both artifacts have the same event types in their streams.
        idea_types = {e.type for e in store.get_events(idea_artifact)}
        review_types = {e.type for e in store.get_events(review_artifact)}
        # Both should have PARK, CHALLENGE, ANSWER, VERDICT.
        expected = {PARK, CHALLENGE, ANSWER, VERDICT}
        assert expected.issubset(idea_types)
        assert expected.issubset(review_types)


# ===========================================================================
# Fix H2: park -> grill integration test using real ParkService
# ===========================================================================


class TestParkToGrillIntegration:
    """End-to-end: ParkService.park() -> GrillService full cycle -> confirmed verdict."""

    def test_park_service_to_grill_survive_confirmed(self, store, event_svc, svc):
        """Use ParkService to create artifact+claim, then grill to confirmed survive."""
        park_svc = ParkService(store, event_svc, repo=InMemoryRepository())

        # Park creates real artifact + claim with auto-generated IDs.
        artifact, claim = park_svc.park("lib-1", "Test hypothesis", kind="idea")

        # Transition gate.
        svc.start_grill(artifact.id, artifact.kind)

        # Full grill cycle using the real claim.id.
        challenge = svc.challenge(artifact.id, claim.id, "What evidence?")
        answer = svc.answer(artifact.id, claim.id, "Study X shows Y")
        verdict_ev = svc.verdict(artifact.id, claim.id, "survive", "Evidence is solid")

        # Confirm system events via EventService.
        event_svc.confirm_event(artifact.id, challenge.id)
        event_svc.confirm_event(artifact.id, verdict_ev.id)

        # Assert claim_status returns "survived" using the real claim.id.
        events = store.get_events(artifact.id)
        assert claim_status(events, claim.id) == "survived"

        # Assert the full event stream has the expected event types.
        event_types = [e.type for e in events]
        assert PARK in event_types
        assert CHALLENGE in event_types
        assert ANSWER in event_types
        assert VERDICT in event_types
        assert CONFIRM in event_types


# ===========================================================================
# auto_challenge (LLM-powered)
# ===========================================================================


class TestAutoChallenge:
    def test_creates_event_confirmed_false(self):
        """auto_challenge produces CHALLENGE event with confirmed=False, actor=system."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = FakeLLMClient([json.dumps({"question": "How do you know?", "target_aspect": "evidence"})])
        svc = GrillService(store, event_svc, llm=llm)
        _park(store)

        event = svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        assert event.type == CHALLENGE
        assert event.confirmed is False
        assert event.actor == "system"
        assert event.payload["question"] == "How do you know?"
        assert event.payload["target_aspect"] == "evidence"
        assert event.payload["auto_generated"] is True

    def test_without_llm_raises(self):
        """auto_challenge raises LLMNotConfiguredError when llm=None."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        svc = GrillService(store, event_svc)  # no llm
        _park(store)

        with pytest.raises(LLMNotConfiguredError, match="not configured"):
            svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

    def test_bad_json_raises(self):
        """auto_challenge raises LLMResponseError on unparseable response."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = FakeLLMClient(["not valid json at all"])
        svc = GrillService(store, event_svc, llm=llm)
        _park(store)

        with pytest.raises(LLMResponseError, match="Failed to parse JSON"):
            svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

    def test_empty_question_raises(self):
        """auto_challenge raises LLMResponseError when question is empty."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = FakeLLMClient([json.dumps({"question": "", "target_aspect": "logic"})])
        svc = GrillService(store, event_svc, llm=llm)
        _park(store)

        with pytest.raises(LLMResponseError, match="empty challenge question"):
            svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

    def test_validates_artifact_was_parked(self):
        """auto_challenge on empty artifact raises ValueError."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = FakeLLMClient([json.dumps({"question": "Why?", "target_aspect": "logic"})])
        svc = GrillService(store, event_svc, llm=llm)

        with pytest.raises(ValueError, match="has no events"):
            svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")


# ===========================================================================
# auto_verdict (LLM-powered)
# ===========================================================================


class TestAutoVerdict:
    def test_survive_confirmed_false(self):
        """auto_verdict survive has confirmed=False, payload has outcome/rationale/confidence."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = FakeLLMClient([json.dumps({"outcome": "survive", "rationale": "Evidence holds up", "confidence": 0.85})])
        svc = GrillService(store, event_svc, llm=llm)
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")

        event = svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Why?", "Because study Z")

        assert event.type == VERDICT
        assert event.confirmed is False
        assert event.actor == "system"
        assert event.payload["outcome"] == "survive"
        assert event.payload["rationale"] == "Evidence holds up"
        assert event.payload["confidence"] == 0.85
        assert event.payload["auto_generated"] is True

    def test_records_challenge_id_when_provided(self):
        """auto_verdict(challenge_id=...) records it in the VERDICT payload."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = FakeLLMClient([json.dumps({"outcome": "survive", "rationale": "OK", "confidence": 0.8})])
        svc = GrillService(store, event_svc, llm=llm)
        _park(store)
        challenge = svc.challenge(ARTIFACT, CLAIM_A, "Why?")

        event = svc.auto_verdict(
            ARTIFACT, CLAIM_A, "X causes Y", "Why?", "Because Z",
            challenge_id=challenge.id,
        )
        assert event.payload["challenge_id"] == challenge.id

    def test_omits_challenge_id_when_not_provided(self):
        """Without challenge_id, the auto_verdict payload carries no challenge_id."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = FakeLLMClient([json.dumps({"outcome": "survive", "rationale": "OK", "confidence": 0.8})])
        svc = GrillService(store, event_svc, llm=llm)
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")

        event = svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Why?", "Because Z")
        assert "challenge_id" not in event.payload

    def test_kill_confirmed_false(self):
        """auto_verdict kill has confirmed=False."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = FakeLLMClient([json.dumps({"outcome": "kill", "rationale": "No evidence", "confidence": 0.9, "death_cause": "refuted"})])
        svc = GrillService(store, event_svc, llm=llm)
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Prove it")

        event = svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Prove it", "I cannot")

        assert event.type == VERDICT
        assert event.confirmed is False
        assert event.payload["outcome"] == "kill"
        assert event.payload["auto_generated"] is True

    def test_invalid_outcome_raises(self):
        """auto_verdict raises LLMResponseError on invalid outcome (e.g. 'maybe')."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = FakeLLMClient([json.dumps({"outcome": "maybe", "rationale": "unsure", "confidence": 0.5})])
        svc = GrillService(store, event_svc, llm=llm)
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")

        with pytest.raises(LLMResponseError, match="invalid verdict outcome"):
            svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Why?", "Because")

    def test_without_llm_raises(self):
        """auto_verdict raises LLMNotConfiguredError when llm=None."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        svc = GrillService(store, event_svc)  # no llm
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")

        with pytest.raises(LLMNotConfiguredError, match="not configured"):
            svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Why?", "Because")

    def test_requires_prior_challenge(self):
        """auto_verdict on parked-only artifact (no challenge) raises ValueError."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = FakeLLMClient([json.dumps({"outcome": "survive", "rationale": "OK", "confidence": 0.8})])
        svc = GrillService(store, event_svc, llm=llm)
        _park(store)

        with pytest.raises(ValueError, match="No challenge exists"):
            svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Why?", "Because")


# ===========================================================================
# Evidence-aware auto-grill (P1: 观点对辩 → 证据对辩)
# ===========================================================================


from anneal.domain.models import Material
from anneal.services.grounding_service import GroundingService
from anneal.store.repository import InMemoryRepository
from tests.fakes import CapturingLLMClient


def _seed_confirmed_ground(
    store, event_svc, verdict: str, title: str = "Landmark RCT"
):
    """Realistically seed a CONFIRMED ground event for CLAIM_A on ARTIFACT.

    Goes through GroundingService.ground (PENDING) + EventService.confirm_event,
    so the confirmed-via-CONFIRM path is exercised (the ground event's own
    confirmed flag stays False — append-only).
    """
    repo = InMemoryRepository()
    material = Material(
        library_id="lib-1",
        kind="paper",
        provenance={"source": "arxiv"},
        payload={"title": title, "abstract": "..."},
    )
    repo.create_material(material)
    grounding = GroundingService(store, event_svc, repo)
    ground_ev = grounding.ground(
        ARTIFACT,
        CLAIM_A,
        material.id,
        verdict=verdict,
        evidence="effect size 0.8",
        assessment="strong" if verdict == "supports" else "refutes",
    )
    event_svc.confirm_event(ARTIFACT, ground_ev.id)
    return ground_ev


class TestAutoChallengeEvidenceAware:
    def test_confirmed_ground_evidence_in_prompt(self):
        """auto_challenge surfaces a confirmed ground event in the LLM prompt."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = CapturingLLMClient([json.dumps({"question": "Q?", "target_aspect": "scope"})])
        svc = GrillService(store, event_svc, llm=llm)
        _park(store)
        ground_ev = _seed_confirmed_ground(store, event_svc, verdict="supports", title="Landmark RCT")

        event = svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        assert "Literature evidence:" in llm.last_user
        assert "Landmark RCT" in llm.last_user
        assert "SUPPORTS" in llm.last_user

        # Provenance recorded on the challenge event payload.
        assert event.payload["evidence_count"] > 0
        assert ground_ev.payload["material_id"] in event.payload["grounded_material_ids"]

    def test_silent_ground_excluded_from_prompt_and_provenance(self):
        """A confirmed SILENT ground (查无) bears nothing on the claim — it
        never enters the evidence block and never inflates evidence_count."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = CapturingLLMClient([json.dumps({"question": "Q?", "target_aspect": "scope"})])
        svc = GrillService(store, event_svc, llm=llm)
        _park(store)
        _seed_confirmed_ground(store, event_svc, verdict="silent", title="Unrelated Survey")

        event = svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        assert "Literature evidence:" not in llm.last_user
        assert "Unrelated Survey" not in llm.last_user
        assert event.payload["evidence_count"] == 0
        assert event.payload["grounded_material_ids"] == []

    def test_pending_ground_not_in_prompt(self):
        """A PENDING (unconfirmed) ground event must NOT leak into the prompt."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = CapturingLLMClient([json.dumps({"question": "Q?", "target_aspect": "scope"})])
        svc = GrillService(store, event_svc, llm=llm)
        _park(store)
        # Ground but DO NOT confirm.
        repo = InMemoryRepository()
        material = Material(library_id="lib-1", kind="paper",
                            provenance={"source": "arxiv"}, payload={"title": "Unconfirmed"})
        repo.create_material(material)
        GroundingService(store, event_svc, repo).ground(
            ARTIFACT, CLAIM_A, material.id, verdict="supports"
        )

        svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        assert "Literature evidence:" not in llm.last_user
        assert "Unconfirmed" not in llm.last_user

    def test_no_ground_evidence_no_block(self):
        """No ground events at all -> no evidence block in the prompt."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = CapturingLLMClient([json.dumps({"question": "Q?", "target_aspect": "scope"})])
        svc = GrillService(store, event_svc, llm=llm)
        _park(store)

        event = svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        assert "Literature evidence:" not in llm.last_user
        # Provenance recorded honestly even with no evidence.
        assert event.payload["evidence_count"] == 0
        assert event.payload["grounded_material_ids"] == []


class TestAutoVerdictEvidenceAware:
    def test_confirmed_ground_evidence_in_prompt(self):
        """auto_verdict surfaces a confirmed ground event in the LLM prompt."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = CapturingLLMClient(
            [json.dumps({"outcome": "kill", "rationale": "r", "confidence": 0.9, "death_cause": "refuted"})]
        )
        svc = GrillService(store, event_svc, llm=llm)
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")
        ground_ev = _seed_confirmed_ground(store, event_svc, verdict="contradicts", title="Refuting Study")

        event = svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Why?", "Because")

        assert "Literature evidence:" in llm.last_user
        assert "Refuting Study" in llm.last_user
        assert "CONTRADICTS" in llm.last_user

        # Provenance recorded on the verdict event payload.
        assert event.payload["evidence_count"] > 0
        assert ground_ev.payload["material_id"] in event.payload["grounded_material_ids"]

    def test_no_ground_evidence_no_block(self):
        """No confirmed ground evidence -> no evidence block in verdict prompt."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = CapturingLLMClient(
            [json.dumps({"outcome": "survive", "rationale": "r", "confidence": 0.8})]
        )
        svc = GrillService(store, event_svc, llm=llm)
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")

        event = svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Why?", "Because")

        assert "Literature evidence:" not in llm.last_user
        # Provenance recorded honestly even with no evidence.
        assert event.payload["evidence_count"] == 0
        assert event.payload["grounded_material_ids"] == []


# ===========================================================================
# 死因分诊 (death-cause triage) — spec docs/spec-verdict-precedent.md §2
# ===========================================================================


class TestVerdictDeathTriage:
    def _grill(self, svc, store):
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")

    def test_kill_without_death_cause_rejected(self, svc, store):
        self._grill(svc, store)
        with pytest.raises(ValueError, match="death_cause"):
            svc.verdict(ARTIFACT, CLAIM_A, "kill", "wrong")

    def test_kill_with_unknown_death_cause_rejected(self, svc, store):
        self._grill(svc, store)
        with pytest.raises(ValueError, match="death_cause"):
            svc.verdict(ARTIFACT, CLAIM_A, "kill", "wrong", death_cause="tragic")

    @pytest.mark.parametrize("cause", ["refuted", "not_worth", "boundary"])
    def test_terminal_causes_accepted(self, svc, store, cause):
        self._grill(svc, store)
        event = svc.verdict(ARTIFACT, CLAIM_A, "kill", "r", death_cause=cause)
        assert event.payload["death_cause"] == cause
        assert "revival_condition" not in event.payload
        assert "successor_claim_id" not in event.payload

    def test_circumstantial_without_revival_condition_rejected(self, svc, store):
        """想不出复活条件 = 该选品味死 — the structure forces it."""
        self._grill(svc, store)
        with pytest.raises(ValueError, match="revival_condition"):
            svc.verdict(
                ARTIFACT, CLAIM_A, "kill", "r", death_cause="circumstantial"
            )

    def test_circumstantial_with_blank_revival_condition_rejected(self, svc, store):
        self._grill(svc, store)
        with pytest.raises(ValueError, match="revival_condition"):
            svc.verdict(
                ARTIFACT, CLAIM_A, "kill", "r",
                death_cause="circumstantial", revival_condition="   ",
            )

    def test_circumstantial_with_revival_condition_accepted(self, svc, store):
        self._grill(svc, store)
        event = svc.verdict(
            ARTIFACT, CLAIM_A, "kill", "cannot defend today",
            death_cause="circumstantial",
            revival_condition="Tier 1 proof insufficient AND embedding accepted",
        )
        assert event.payload["death_cause"] == "circumstantial"
        assert (
            event.payload["revival_condition"]
            == "Tier 1 proof insufficient AND embedding accepted"
        )

    def test_revival_condition_on_non_circumstantial_rejected(self, svc, store):
        self._grill(svc, store)
        with pytest.raises(ValueError, match="circumstantial"):
            svc.verdict(
                ARTIFACT, CLAIM_A, "kill", "r",
                death_cause="refuted", revival_condition="if pigs fly",
            )

    def test_boundary_with_successor_accepted(self, svc, store):
        self._grill(svc, store)
        event = svc.verdict(
            ARTIFACT, CLAIM_A, "kill", "over-broad",
            death_cause="boundary", successor_claim_id="claim-narrow",
        )
        assert event.payload["death_cause"] == "boundary"
        assert event.payload["successor_claim_id"] == "claim-narrow"

    def test_boundary_without_successor_accepted(self, svc, store):
        """successor_claim_id is OPTIONAL for boundary kills."""
        self._grill(svc, store)
        event = svc.verdict(
            ARTIFACT, CLAIM_A, "kill", "over-broad", death_cause="boundary"
        )
        assert "successor_claim_id" not in event.payload

    @pytest.mark.parametrize("cause", ["refuted", "not_worth"])
    def test_successor_on_non_boundary_rejected(self, svc, store, cause):
        self._grill(svc, store)
        with pytest.raises(ValueError, match="boundary"):
            svc.verdict(
                ARTIFACT, CLAIM_A, "kill", "r",
                death_cause=cause, successor_claim_id="claim-narrow",
            )

    def test_survive_with_death_cause_rejected(self, svc, store):
        self._grill(svc, store)
        with pytest.raises(ValueError, match="death_cause"):
            svc.verdict(
                ARTIFACT, CLAIM_A, "survive", "ok", death_cause="refuted"
            )

    def test_survive_with_revival_condition_rejected(self, svc, store):
        self._grill(svc, store)
        with pytest.raises(ValueError, match="revival_condition"):
            svc.verdict(
                ARTIFACT, CLAIM_A, "survive", "ok", revival_condition="later"
            )

    def test_survive_with_successor_rejected(self, svc, store):
        self._grill(svc, store)
        with pytest.raises(ValueError, match="successor_claim_id"):
            svc.verdict(
                ARTIFACT, CLAIM_A, "survive", "ok", successor_claim_id="c2"
            )

    def test_plain_survive_untouched(self, svc, store):
        """survive without triage fields keeps the legacy payload shape."""
        self._grill(svc, store)
        event = svc.verdict(ARTIFACT, CLAIM_A, "survive", "ok")
        for key in ("death_cause", "revival_condition", "successor_claim_id"):
            assert key not in event.payload

    def test_bypass_untouched(self, svc, store):
        """bypass (debt survive) never carries triage fields."""
        self._grill(svc, store)
        event = svc.bypass(ARTIFACT, CLAIM_A)
        assert event.payload["outcome"] == "survive"
        for key in ("death_cause", "revival_condition", "successor_claim_id"):
            assert key not in event.payload


class TestAutoVerdictDeathTriage:
    def _svc(self, responses):
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = FakeLLMClient([json.dumps(r) for r in responses])
        svc = GrillService(store, event_svc, llm=llm)
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Prove it")
        return svc

    def test_kill_with_proposed_cause_recorded(self):
        svc = self._svc([
            {"outcome": "kill", "rationale": "r", "confidence": 0.9,
             "death_cause": "not_worth", "revival_condition": None}
        ])
        event = svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Prove it", "I cannot")
        assert event.payload["death_cause"] == "not_worth"
        assert "revival_condition" not in event.payload
        assert event.confirmed is False  # still the human CONFIRM gate

    def test_kill_missing_death_cause_raises(self):
        svc = self._svc([
            {"outcome": "kill", "rationale": "r", "confidence": 0.9}
        ])
        with pytest.raises(LLMResponseError, match="death_cause"):
            svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Prove it", "I cannot")

    def test_kill_invalid_death_cause_raises(self):
        svc = self._svc([
            {"outcome": "kill", "rationale": "r", "confidence": 0.9,
             "death_cause": "tragic"}
        ])
        with pytest.raises(LLMResponseError, match="death_cause"):
            svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Prove it", "I cannot")

    def test_circumstantial_without_revival_raises(self):
        svc = self._svc([
            {"outcome": "kill", "rationale": "r", "confidence": 0.9,
             "death_cause": "circumstantial", "revival_condition": None}
        ])
        with pytest.raises(LLMResponseError, match="revival_condition"):
            svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Prove it", "I cannot")

    def test_circumstantial_with_revival_recorded(self):
        svc = self._svc([
            {"outcome": "kill", "rationale": "r", "confidence": 0.9,
             "death_cause": "circumstantial",
             "revival_condition": "dataset D becomes public"}
        ])
        event = svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Prove it", "I cannot")
        assert event.payload["death_cause"] == "circumstantial"
        assert event.payload["revival_condition"] == "dataset D becomes public"

    def test_survive_drops_stray_triage_noise(self):
        """LLM noise on a survive proposal is dropped, not fatal."""
        svc = self._svc([
            {"outcome": "survive", "rationale": "r", "confidence": 0.8,
             "death_cause": "refuted", "revival_condition": "nonsense"}
        ])
        event = svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Prove it", "Because Z")
        assert event.payload["outcome"] == "survive"
        for key in ("death_cause", "revival_condition"):
            assert key not in event.payload

    def test_non_circumstantial_drops_stray_revival(self):
        svc = self._svc([
            {"outcome": "kill", "rationale": "r", "confidence": 0.9,
             "death_cause": "refuted", "revival_condition": "stray"}
        ])
        event = svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Prove it", "I cannot")
        assert event.payload["death_cause"] == "refuted"
        assert "revival_condition" not in event.payload


# ===========================================================================
# 判例先验 (precedent prior) — auto_challenge eats the Library's kill 判例
# spec docs/spec-precedent-prior.md §2 + §4 acceptance 1-6
# ===========================================================================


from datetime import datetime, timedelta

from anneal.domain.events import Event
from anneal.domain.models import Artifact, Claim
from anneal.llm.prompts import build_challenge_prompt, build_verdict_prompt

LIBRARY = "lib-1"
CHALLENGE_RESPONSE = json.dumps({"question": "Q?", "target_aspect": "scope"})


def _repo_with_current_artifact(artifact_id: str = ARTIFACT, library_id: str = LIBRARY):
    """Repository where the artifact under grill resolves to ``library_id``."""
    repo = InMemoryRepository()
    repo.create_artifact(
        Artifact(id=artifact_id, library_id=library_id, kind="idea", goal="g")
    )
    return repo


def _seed_ruled_claim(
    store,
    repo,
    claim_id: str,
    body: str,
    *,
    outcome: str = "kill",
    death_cause: str | None = "refuted",
    rationale: str = "the held-out set leaked",
    revival_condition: str | None = None,
    ts: datetime | None = None,
    library_id: str = LIBRARY,
    confirmed: bool = True,
    artifact_id: str | None = None,
):
    """A Library claim parked in its own artifact, ruled on by a VERDICT.

    Mirrors reality: precedents come from OTHER artifacts in the same Library
    (Library 内穿透), and only a confirmed verdict counts as a 判例.
    """
    artifact_id = artifact_id or f"artifact-{claim_id}"
    if repo.get_artifact(artifact_id) is None:
        repo.create_artifact(
            Artifact(id=artifact_id, library_id=library_id, kind="idea", goal="g")
        )
    repo.create_claim(
        Claim(id=claim_id, library_id=library_id, body=body, artifact_ids=[artifact_id])
    )
    payload: dict = {"outcome": outcome, "rationale": rationale}
    if outcome == "kill" and death_cause is not None:
        payload["death_cause"] = death_cause
    if revival_condition is not None:
        payload["revival_condition"] = revival_condition
    store.append(
        artifact_id,
        Event(
            type=VERDICT,
            actor="system",
            confirmed=confirmed,
            target_ref=claim_id,
            ts=ts or datetime(2026, 1, 1),
            payload=payload,
        ),
    )
    return artifact_id


class TestAutoChallengePrecedentPrior:
    def _svc(self, store, event_svc, repo, responses=None):
        llm = CapturingLLMClient(responses or [CHALLENGE_RESPONSE])
        return GrillService(store, event_svc, llm=llm, repo=repo), llm

    def test_kill_precedent_reaches_the_prompt(self):
        """Acceptance 1: the 判例四元组 is injected into the mainline question."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        repo = _repo_with_current_artifact()
        _seed_ruled_claim(
            store, repo, "past-kill",
            "deep learning beats radiologists on chest X-rays",
            death_cause="refuted", rationale="the held-out set leaked",
        )
        svc, llm = self._svc(store, event_svc, repo)
        _park(store)

        svc.auto_challenge(ARTIFACT, CLAIM_A, "MRI segmentation transfers across scanners")

        assert "past-kill" in llm.last_user
        assert "deep learning beats radiologists on chest X-rays" in llm.last_user
        assert "refuted" in llm.last_user
        assert "the held-out set leaked" in llm.last_user

    def test_rationale_truncated_to_300_chars(self):
        """Acceptance 1: the deterministic 300-char cap holds end to end."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        repo = _repo_with_current_artifact()
        _seed_ruled_claim(store, repo, "past-kill", "old claim", rationale="z" * 500)
        svc, llm = self._svc(store, event_svc, repo)
        _park(store)

        svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        assert "z" * 300 + "…" in llm.last_user
        assert "z" * 301 not in llm.last_user

    def test_cross_topic_kill_still_injected(self):
        """The reason 判例先验 is NOT topic-prefiltered (Q3): zero lexical
        overlap must not cost a precedent its seat."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        repo = _repo_with_current_artifact()
        _seed_ruled_claim(
            store, repo, "past-kill", "tumour imaging models generalize across hospitals"
        )
        svc, llm = self._svc(store, event_svc, repo)
        _park(store)

        svc.auto_challenge(ARTIFACT, CLAIM_A, "厨房油烟与哮喘发病率相关")

        assert "past-kill" in llm.last_user

    def test_survive_precedent_never_injected(self):
        """Acceptance 2 / 前功赦免: survive 判例 are structurally excluded."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        repo = _repo_with_current_artifact()
        _seed_ruled_claim(
            store, repo, "past-survivor", "pretraining helps low-data regimes",
            outcome="survive", death_cause=None, rationale="held up under grilling",
        )
        svc, llm = self._svc(store, event_svc, repo)
        _park(store)

        event = svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        assert "past-survivor" not in llm.last_user
        assert "pretraining helps low-data regimes" not in llm.last_user
        assert "held up under grilling" not in llm.last_user
        assert event.payload["precedent_refs"] == []
        # No kills at all ⇒ today's prompt, verbatim.
        assert (llm.last_system, llm.last_user) == build_challenge_prompt(
            "X causes Y", "", ""
        )

    def test_no_kill_precedents_prompt_is_legacy_verbatim(self):
        """Acceptance 4: cold start degrades to today's prompt, never silence."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        repo = _repo_with_current_artifact()
        svc, llm = self._svc(store, event_svc, repo)
        _park(store)

        event = svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y", "background")

        assert (llm.last_system, llm.last_user) == build_challenge_prompt(
            "X causes Y", "background", ""
        )
        assert event.payload["precedent_refs"] == []

    def test_without_repo_prompt_is_legacy_verbatim(self):
        """Legacy construction (no repo) keeps working — nothing to collect."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = CapturingLLMClient([CHALLENGE_RESPONSE])
        svc = GrillService(store, event_svc, llm=llm)  # no repo
        _park(store)

        event = svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        assert (llm.last_system, llm.last_user) == build_challenge_prompt(
            "X causes Y", "", ""
        )
        assert event.payload["precedent_refs"] == []

    def test_unresolvable_artifact_degrades_silently(self):
        """Artifact not in the repository ⇒ no Library scope ⇒ no precedents."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        repo = InMemoryRepository()  # ARTIFACT never registered
        svc, llm = self._svc(store, event_svc, repo)
        _park(store)

        svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        assert (llm.last_system, llm.last_user) == build_challenge_prompt(
            "X causes Y", "", ""
        )

    def test_current_claim_is_not_its_own_precedent(self):
        store = InMemoryEventStore()
        event_svc = EventService(store)
        repo = _repo_with_current_artifact()
        _seed_ruled_claim(
            store, repo, CLAIM_A, "the claim being grilled", artifact_id=ARTIFACT
        )
        svc, llm = self._svc(store, event_svc, repo)
        _park(store)

        svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        assert "the claim being grilled" not in llm.last_user

    def test_other_library_kill_is_walled_off(self):
        """跨库硬墙 — a kill in another Library never crosses over."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        repo = _repo_with_current_artifact()
        _seed_ruled_claim(
            store, repo, "foreign-kill", "someone else's dead idea", library_id="lib-2"
        )
        svc, llm = self._svc(store, event_svc, repo)
        _park(store)

        svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        assert "foreign-kill" not in llm.last_user
        assert "someone else's dead idea" not in llm.last_user

    def test_unconfirmed_kill_verdict_is_not_a_precedent(self):
        """Trust chain: only confirmed verdicts are 判例 (human-signed)."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        repo = _repo_with_current_artifact()
        _seed_ruled_claim(
            store, repo, "draft-kill", "machine-drafted kill", confirmed=False
        )
        svc, llm = self._svc(store, event_svc, repo)
        _park(store)

        svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        assert "draft-kill" not in llm.last_user
        assert "machine-drafted kill" not in llm.last_user

    def test_budget_keeps_twelve_most_recent(self):
        """Acceptance 6: >12 kills ⇒ ts 倒序取最近 12（可断言）."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        repo = _repo_with_current_artifact()
        for i in range(15):
            _seed_ruled_claim(
                store, repo, f"kill-{i:02d}", f"dead idea number {i:02d}",
                ts=datetime(2026, 1, 1) + timedelta(days=i),
            )
        svc, llm = self._svc(store, event_svc, repo)
        _park(store)

        svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        injected = [i for i in range(15) if f"kill-{i:02d}" in llm.last_user]
        assert injected == list(range(3, 15))  # the 12 newest, the 3 oldest dropped

    def test_precedent_refs_recorded_on_the_event(self):
        """Q5: which 判例 shaped this question is recorded, not inferred."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        repo = _repo_with_current_artifact()
        _seed_ruled_claim(store, repo, "kill-1", "dead idea one")
        _seed_ruled_claim(store, repo, "kill-2", "dead idea two")
        svc, llm = self._svc(store, event_svc, repo, responses=[json.dumps(
            {"question": "Q?", "target_aspect": "scope",
             "precedent_refs": ["kill-2"]}
        )])
        _park(store)

        event = svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        assert event.payload["precedent_refs"] == ["kill-2"]

    def test_hallucinated_precedent_refs_dropped(self):
        """Acceptance 5: ids outside the injected set are dropped."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        repo = _repo_with_current_artifact()
        _seed_ruled_claim(store, repo, "kill-1", "dead idea one")
        svc, llm = self._svc(store, event_svc, repo, responses=[json.dumps(
            {"question": "Q?", "target_aspect": "scope",
             "precedent_refs": ["kill-1", "claim-that-never-existed", 42, None]}
        )])
        _park(store)

        event = svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        assert event.payload["precedent_refs"] == ["kill-1"]

    def test_precedent_refs_deduped_and_ordered(self):
        store = InMemoryEventStore()
        event_svc = EventService(store)
        repo = _repo_with_current_artifact()
        _seed_ruled_claim(store, repo, "kill-1", "dead idea one")
        _seed_ruled_claim(store, repo, "kill-2", "dead idea two")
        svc, llm = self._svc(store, event_svc, repo, responses=[json.dumps(
            {"question": "Q?", "target_aspect": "scope",
             "precedent_refs": ["kill-2", "kill-1", "kill-2"]}
        )])
        _park(store)

        event = svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        assert event.payload["precedent_refs"] == ["kill-2", "kill-1"]

    def test_malformed_precedent_refs_tolerated(self):
        """A non-list precedent_refs is noise, not a fatal response."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        repo = _repo_with_current_artifact()
        _seed_ruled_claim(store, repo, "kill-1", "dead idea one")
        svc, llm = self._svc(store, event_svc, repo, responses=[json.dumps(
            {"question": "Q?", "target_aspect": "scope",
             "precedent_refs": "kill-1"}
        )])
        _park(store)

        event = svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        assert event.payload["precedent_refs"] == []

    def test_existing_payload_fields_unchanged(self):
        """判例先验 is additive — the evidence provenance keeps its shape."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        repo = _repo_with_current_artifact()
        _seed_ruled_claim(store, repo, "kill-1", "dead idea one")
        svc, llm = self._svc(store, event_svc, repo)
        _park(store)
        _seed_confirmed_ground(store, event_svc, verdict="supports", title="Landmark RCT")

        event = svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        assert event.payload["auto_generated"] is True
        assert event.payload["question"] == "Q?"
        assert event.payload["target_aspect"] == "scope"
        assert event.payload["evidence_count"] == 1
        assert len(event.payload["grounded_material_ids"]) == 1
        # Evidence and precedents coexist in one prompt.
        assert "Literature evidence:" in llm.last_user
        assert "kill-1" in llm.last_user


class TestAutoVerdictNeverEatsPrecedents:
    """Acceptance 3 — 铁律 (spec §2 Q2): verdict 侧永不吃判例.

    auto_challenge eating precedents is 取证; auto_verdict eating them would be
    前科定罪 (kill because similar claims died before). This is a REGRESSION
    test — it exists to fail loudly if someone "wires it up here too".
    """

    def _setup(self):
        store = InMemoryEventStore()
        event_svc = EventService(store)
        repo = _repo_with_current_artifact()
        _seed_ruled_claim(
            store, repo, "past-kill", "deep learning beats radiologists",
            death_cause="not_worth", rationale="not worth the annotation budget",
        )
        _seed_ruled_claim(
            store, repo, "past-kill-2", "another dead idea",
            death_cause="circumstantial", rationale="shelved",
            revival_condition="dataset D goes public",
        )
        llm = CapturingLLMClient([json.dumps(
            {"outcome": "kill", "rationale": "r", "confidence": 0.9,
             "death_cause": "refuted"}
        )])
        svc = GrillService(store, event_svc, llm=llm, repo=repo)
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Prove it")
        return svc, llm

    def test_verdict_prompt_is_byte_identical_to_the_no_precedent_prompt(self):
        svc, llm = self._setup()

        svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Prove it", "I cannot")

        assert (llm.last_system, llm.last_user) == build_verdict_prompt(
            "X causes Y", "Prove it", "I cannot", ""
        )

    def test_no_precedent_content_anywhere_in_the_verdict_prompt(self):
        svc, llm = self._setup()

        svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Prove it", "I cannot")

        prompt = llm.last_system + llm.last_user
        for leak in (
            "past-kill",
            "deep learning beats radiologists",
            "not worth the annotation budget",
            "dataset D goes public",
            "Death cause:",
            "Verdict rationale:",
            "precedent_refs",
        ):
            assert leak not in prompt

    def test_verdict_payload_carries_no_precedent_refs(self):
        svc, llm = self._setup()

        event = svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Prove it", "I cannot")

        assert "precedent_refs" not in event.payload
