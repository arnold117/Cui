"""Tests for anneal.services.promote_service — promote survived claims into DOC."""

import pytest

from anneal.domain.events import (
    ANSWER,
    CHALLENGE,
    CONFIRM,
    DRAFT,
    PARK,
    PROMOTE,
    RETRACT,
    VERDICT,
    make_event,
)
from anneal.domain.invariants import DebtBlockError, KilledClaimError, UngrilledError
from anneal.domain.projections import claim_status
from anneal.services.event_service import EventService
from anneal.services.grill_service import GrillService
from anneal.services.park_service import ParkService
from anneal.services.promote_service import PromoteService
from anneal.store.event_store import InMemoryEventStore
from anneal.store.repository import InMemoryRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
def promote_svc(store, event_svc):
    return PromoteService(store, event_svc)


# ---------------------------------------------------------------------------
# Helpers — build a fully grilled artifact
# ---------------------------------------------------------------------------


def _park_and_grill_survive(
    park_svc: ParkService,
    grill_svc: GrillService,
    event_svc: EventService,
    *,
    confirm_verdict: bool = True,
    bypass: bool = False,
) -> tuple[str, str]:
    """Create a parked artifact, grill it, and survive the claim.

    Returns (artifact_id, claim_id).
    If bypass=True, uses bypass() instead of the full challenge-answer-verdict cycle.
    If confirm_verdict=True, confirms system events (challenge and verdict).
    """
    artifact, claim = park_svc.park("lib-1", "Test hypothesis", kind="idea")

    grill_svc.start_grill(artifact.id, artifact.kind)

    if bypass:
        # bypass requires at least one challenge to exist
        challenge = grill_svc.challenge(artifact.id, claim.id, "What evidence?")
        if confirm_verdict:
            event_svc.confirm_event(artifact.id, challenge.id)
        bypass_evt = grill_svc.bypass(artifact.id, claim.id)
        if confirm_verdict:
            event_svc.confirm_event(artifact.id, bypass_evt.id)
        return artifact.id, claim.id

    challenge = grill_svc.challenge(artifact.id, claim.id, "What evidence?")
    _answer = grill_svc.answer(artifact.id, claim.id, "Study X shows Y")
    verdict_evt = grill_svc.verdict(
        artifact.id, claim.id, "survive", "Evidence is solid",
    )

    if confirm_verdict:
        event_svc.confirm_event(artifact.id, challenge.id)
        event_svc.confirm_event(artifact.id, verdict_evt.id)

    return artifact.id, claim.id


def _park_and_grill_kill(
    park_svc: ParkService,
    grill_svc: GrillService,
    event_svc: EventService,
) -> tuple[str, str]:
    """Create a parked artifact, grill it, and kill the claim.

    Returns (artifact_id, claim_id).
    """
    artifact, claim = park_svc.park("lib-1", "Bad hypothesis", kind="idea")

    grill_svc.start_grill(artifact.id, artifact.kind)

    challenge = grill_svc.challenge(artifact.id, claim.id, "Prove this")
    _answer = grill_svc.answer(artifact.id, claim.id, "I cannot")
    verdict_evt = grill_svc.verdict(
        artifact.id, claim.id, "kill", "No evidence",
    )

    event_svc.confirm_event(artifact.id, challenge.id)
    event_svc.confirm_event(artifact.id, verdict_evt.id)

    return artifact.id, claim.id


# ===========================================================================
# promote
# ===========================================================================


class TestPromoteSuccess:
    def test_promote_survived_confirmed_no_debt(
        self, park_svc, grill_svc, event_svc, promote_svc, store,
    ):
        """Promote succeeds for a survived, confirmed, no-debt claim.

        A PROMOTE event is appended to the store.
        """
        artifact_id, claim_id = _park_and_grill_survive(
            park_svc, grill_svc, event_svc,
        )

        evt = promote_svc.promote(artifact_id, claim_id)

        assert evt.type == PROMOTE
        assert evt.actor == "user"
        assert evt.target_ref == claim_id
        assert evt.confirmed is True

        # Event is in the store.
        events = store.get_events(artifact_id)
        assert evt in events


class TestPromoteDebtBlock:
    def test_promote_raises_on_debt_bearing_claim(
        self, park_svc, grill_svc, event_svc, promote_svc, store,
    ):
        """Promote raises DebtBlockError on a claim with unresolved debt.

        A claim that survived grill (confirmed verdict) but then acquired
        a separate debt-bearing event (e.g. an unconfirmed DRAFT with
        debt=True) cannot be promoted until that debt is cleared.

        Note: bypass without confirm raises UngrilledError (not DebtBlockError)
        because the unconfirmed bypass verdict doesn't count as survived.
        The debt gate is only reachable for claims that ARE survived.
        """
        artifact_id, claim_id = _park_and_grill_survive(
            park_svc, grill_svc, event_svc,
        )

        # Inject a debt-bearing event targeting this claim.
        debt_event = make_event(
            type=DRAFT, actor="system", confirmed=False,
            debt=True, target_ref=claim_id,
        )
        store.append(artifact_id, debt_event)

        with pytest.raises(DebtBlockError, match="unresolved debt"):
            promote_svc.promote(artifact_id, claim_id)

    def test_bypass_without_confirm_raises_ungrilled(
        self, park_svc, grill_svc, event_svc, promote_svc,
    ):
        """Bypass without confirm raises UngrilledError, not DebtBlockError.

        An unconfirmed bypass verdict doesn't count as survived, so the
        invariant check hits UngrilledError before reaching the debt gate.
        """
        artifact_id, claim_id = _park_and_grill_survive(
            park_svc, grill_svc, event_svc, bypass=True, confirm_verdict=False,
        )

        with pytest.raises(UngrilledError, match="has not survived grill"):
            promote_svc.promote(artifact_id, claim_id)


class TestPromoteUngrilledError:
    def test_promote_raises_on_ungrilled_claim(
        self, park_svc, promote_svc,
    ):
        """Promote raises UngrilledError on a claim without a survive verdict."""
        artifact, claim = park_svc.park("lib-1", "Raw idea", kind="idea")

        with pytest.raises(UngrilledError, match="has not survived grill"):
            promote_svc.promote(artifact.id, claim.id)


class TestPromoteKilledClaim:
    def test_promote_raises_on_killed_claim(
        self, park_svc, grill_svc, event_svc, promote_svc,
    ):
        """Promote raises KilledClaimError on a killed claim."""
        artifact_id, claim_id = _park_and_grill_kill(
            park_svc, grill_svc, event_svc,
        )

        with pytest.raises(KilledClaimError, match="has been killed"):
            promote_svc.promote(artifact_id, claim_id)


class TestPromoteAfterDebtCleared:
    def test_promote_succeeds_after_debt_cleared(
        self, park_svc, grill_svc, event_svc, promote_svc, store,
    ):
        """Promote succeeds after debt is cleared via EventService.confirm_event.

        Flow: survive (confirmed) -> add debt-bearing event -> fail ->
              confirm debt event -> promote succeeds.
        """
        artifact_id, claim_id = _park_and_grill_survive(
            park_svc, grill_svc, event_svc,
        )

        # Inject a debt-bearing event targeting this claim.
        debt_event = make_event(
            type=DRAFT, actor="system", confirmed=False,
            debt=True, target_ref=claim_id,
        )
        store.append(artifact_id, debt_event)

        # Debt is unresolved — promote should fail.
        with pytest.raises(DebtBlockError):
            promote_svc.promote(artifact_id, claim_id)

        # Clear the debt by confirming the debt-bearing event.
        event_svc.confirm_event(artifact_id, debt_event.id)

        # Now promote should succeed.
        evt = promote_svc.promote(artifact_id, claim_id)
        assert evt.type == PROMOTE
        assert evt.target_ref == claim_id

    def test_bypass_confirm_clears_debt_and_enables_promote(
        self, park_svc, grill_svc, event_svc, promote_svc,
    ):
        """Confirming a bypass verdict both marks the claim survived AND
        clears the debt, enabling promote in one step."""
        artifact, claim = park_svc.park("lib-1", "Bypassed idea", kind="idea")
        grill_svc.start_grill(artifact.id, artifact.kind)
        grill_svc.challenge(artifact.id, claim.id, "What evidence?")

        bypass_evt = grill_svc.bypass(artifact.id, claim.id)

        # Before confirm: unconfirmed bypass -> UngrilledError.
        with pytest.raises(UngrilledError):
            promote_svc.promote(artifact.id, claim.id)

        # Confirm the bypass verdict — this both marks survived AND clears debt.
        event_svc.confirm_event(artifact.id, bypass_evt.id)

        # Now promote succeeds.
        evt = promote_svc.promote(artifact.id, claim.id)
        assert evt.type == PROMOTE
        assert evt.target_ref == claim.id


# ===========================================================================
# reference_claim
# ===========================================================================


class TestReferenceClaimDebtBlock:
    def test_reference_claim_raises_on_debt(
        self, park_svc, grill_svc, event_svc, promote_svc, store,
    ):
        """reference_claim raises DebtBlockError on a debt-bearing claim.

        Uses a survived claim that acquires a separate debt-bearing event.
        """
        artifact_id, claim_id = _park_and_grill_survive(
            park_svc, grill_svc, event_svc,
        )

        # Inject a debt-bearing event targeting this claim.
        debt_event = make_event(
            type=DRAFT, actor="system", confirmed=False,
            debt=True, target_ref=claim_id,
        )
        store.append(artifact_id, debt_event)

        with pytest.raises(DebtBlockError, match="unresolved debt"):
            promote_svc.reference_claim(artifact_id, claim_id)


class TestReferenceClaimSuccess:
    def test_reference_claim_succeeds_on_clean_claim(
        self, park_svc, grill_svc, event_svc, promote_svc,
    ):
        """reference_claim succeeds on a claim with no unresolved debt."""
        artifact_id, claim_id = _park_and_grill_survive(
            park_svc, grill_svc, event_svc,
        )

        # Should not raise.
        promote_svc.reference_claim(artifact_id, claim_id)


# ===========================================================================
# get_doc
# ===========================================================================


class TestGetDocAfterPromote:
    def test_doc_contains_only_clean_content(
        self, park_svc, grill_svc, event_svc, promote_svc, store,
    ):
        """get_doc after promote contains only clean content.

        No killed, no debt, no unconfirmed, no park events.
        """
        artifact_id, claim_id = _park_and_grill_survive(
            park_svc, grill_svc, event_svc,
        )
        promote_svc.promote(artifact_id, claim_id)

        doc = promote_svc.get_doc(artifact_id)

        # DOC must not be empty.
        assert len(doc) > 0

        # "Confirmed" means raw flag set OR a non-retracted CONFIRM event
        # targets it (append-only confirm flow leaves the raw flag False).
        pending_ids = {e.id for e in event_svc.pending_events(artifact_id)}

        for evt in doc:
            # No park events in DOC.
            assert evt.type != PARK, "PARK events must not appear in DOC"
            # No debt-bearing events.
            assert evt.debt is False, "Debt-bearing events must not appear in DOC"
            # No pending (unconfirmed) events.
            assert evt.id not in pending_ids, (
                "Pending (unconfirmed) events must not appear in DOC"
            )
            # No meta-events.
            assert evt.type not in {CONFIRM, RETRACT}, (
                "Meta-events (CONFIRM/RETRACT) must not appear in DOC"
            )
            # No kill verdicts.
            if evt.type == VERDICT:
                assert evt.payload.get("outcome") != "kill", (
                    "Kill verdicts must not appear in DOC"
                )

        # The PROMOTE event for the claim should be present.
        promote_events = [e for e in doc if e.type == PROMOTE]
        assert len(promote_events) == 1
        assert promote_events[0].target_ref == claim_id


class TestGetDocExcludesKilledClaimEvents:
    def test_doc_excludes_events_targeting_killed_claims(
        self, park_svc, grill_svc, event_svc, promote_svc, store,
    ):
        """get_doc does NOT contain events targeting killed claims.

        This tests the doc_projection Fix 4: events whose target_ref
        points to a killed claim are excluded from DOC.
        """
        # Create one artifact with two claims: one survives, one is killed.
        artifact, claim_survive = park_svc.park("lib-1", "Good idea", kind="idea")

        grill_svc.start_grill(artifact.id, artifact.kind)

        # Claim that survives.
        c1 = grill_svc.challenge(artifact.id, claim_survive.id, "Evidence?")
        grill_svc.answer(artifact.id, claim_survive.id, "Study X")
        v1 = grill_svc.verdict(
            artifact.id, claim_survive.id, "survive", "Solid",
        )
        event_svc.confirm_event(artifact.id, c1.id)
        event_svc.confirm_event(artifact.id, v1.id)

        # Second claim that gets killed.
        killed_claim_id = "claim-killed"
        c2 = grill_svc.challenge(artifact.id, killed_claim_id, "Prove this")
        grill_svc.answer(artifact.id, killed_claim_id, "Cannot")
        v2 = grill_svc.verdict(
            artifact.id, killed_claim_id, "kill", "No evidence",
        )
        event_svc.confirm_event(artifact.id, c2.id)
        event_svc.confirm_event(artifact.id, v2.id)

        # Promote the surviving claim.
        promote_svc.promote(artifact.id, claim_survive.id)

        doc = promote_svc.get_doc(artifact.id)

        # No events in DOC should reference the killed claim.
        for evt in doc:
            assert evt.target_ref != killed_claim_id, (
                f"Event {evt.type} targeting killed claim {killed_claim_id!r} "
                f"must not appear in DOC"
            )

        # The surviving claim's events should be present.
        surviving_events = [
            e for e in doc if e.target_ref == claim_survive.id
        ]
        assert len(surviving_events) > 0, (
            "DOC should contain events for the surviving claim"
        )
