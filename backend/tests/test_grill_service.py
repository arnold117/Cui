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
        event = svc.verdict(ARTIFACT, CLAIM_A, "kill", "No supporting evidence")

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
        verdict = svc.verdict(ARTIFACT, CLAIM_A, "kill", "Claim unsupported")

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
        verdict = svc.verdict(ARTIFACT, CLAIM_A, "kill", "No evidence")

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

    def test_kill_confirmed_false(self):
        """auto_verdict kill has confirmed=False."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = FakeLLMClient([json.dumps({"outcome": "kill", "rationale": "No evidence", "confidence": 0.9})])
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
    store, event_svc, supported: bool, title: str = "Landmark RCT"
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
        supported=supported,
        evidence="effect size 0.8",
        assessment="strong" if supported else "refutes",
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
        _seed_confirmed_ground(store, event_svc, supported=True, title="Landmark RCT")

        svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        assert "Literature evidence:" in llm.last_user
        assert "Landmark RCT" in llm.last_user
        assert "SUPPORTS" in llm.last_user

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
            ARTIFACT, CLAIM_A, material.id, supported=True
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

        svc.auto_challenge(ARTIFACT, CLAIM_A, "X causes Y")

        assert "Literature evidence:" not in llm.last_user


class TestAutoVerdictEvidenceAware:
    def test_confirmed_ground_evidence_in_prompt(self):
        """auto_verdict surfaces a confirmed ground event in the LLM prompt."""
        store = InMemoryEventStore()
        event_svc = EventService(store)
        llm = CapturingLLMClient(
            [json.dumps({"outcome": "kill", "rationale": "r", "confidence": 0.9})]
        )
        svc = GrillService(store, event_svc, llm=llm)
        _park(store)
        svc.challenge(ARTIFACT, CLAIM_A, "Why?")
        _seed_confirmed_ground(store, event_svc, supported=False, title="Refuting Study")

        svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Why?", "Because")

        assert "Literature evidence:" in llm.last_user
        assert "Refuting Study" in llm.last_user
        assert "CONTRADICTS" in llm.last_user

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

        svc.auto_verdict(ARTIFACT, CLAIM_A, "X causes Y", "Why?", "Because")

        assert "Literature evidence:" not in llm.last_user
