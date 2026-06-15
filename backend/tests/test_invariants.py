"""Tests for anneal.domain.invariants — business-rule guards."""

import pytest

from anneal.domain.events import (
    CHALLENGE,
    CONFIRM,
    ANSWER,
    PARK,
    PROMOTE,
    RETRACT,
    VERDICT,
    make_event,
)
from anneal.domain.invariants import (
    DebtBlockError,
    KilledClaimError,
    ParkIsolationViolation,
    UngrilledError,
    assert_can_promote,
    assert_claim_no_debt,
    assert_park_isolation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CLAIM_A = "claim-a"


def _verdict(outcome: str, claim_id: str = CLAIM_A, **kw):
    return make_event(
        type=VERDICT,
        actor="system",
        payload={"outcome": outcome},
        target_ref=claim_id,
        **kw,
    )


def _confirm(target_id: str):
    return make_event(type=CONFIRM, actor="user", target_ref=target_id, confirmed=True)


def _retract(target_id: str):
    return make_event(type=RETRACT, actor="user", target_ref=target_id, confirmed=True)


def _grill_survive(claim_id: str = CLAIM_A) -> list:
    """Minimal grill cycle that ends in survive (all confirmed)."""
    return [
        make_event(type=CHALLENGE, actor="system", confirmed=True),
        make_event(type=ANSWER, actor="user", confirmed=True),
        _verdict("survive", claim_id, confirmed=True),
    ]


# ===========================================================================
# assert_can_promote
# ===========================================================================


class TestAssertCanPromote:
    def test_raises_debt_block_error_on_debt(self):
        """Promote is hard-blocked when claim has unresolved debt."""
        bypass_verdict = _verdict("survive", CLAIM_A, debt=True, confirmed=True)
        events = [bypass_verdict]
        with pytest.raises(DebtBlockError):
            assert_can_promote(events, CLAIM_A)

    def test_raises_ungrilled_error_without_survive(self):
        """Promote is hard-blocked when claim never survived grill."""
        challenge = make_event(type=CHALLENGE, actor="system", confirmed=True)
        answer = make_event(type=ANSWER, actor="user", confirmed=True)
        # No verdict at all.
        events = [challenge, answer]
        with pytest.raises(UngrilledError):
            assert_can_promote(events, CLAIM_A)

    def test_raises_killed_claim_error_on_killed(self):
        """Promote is hard-blocked on a killed claim."""
        events = [_verdict("kill", CLAIM_A, confirmed=True)]
        with pytest.raises(KilledClaimError):
            assert_can_promote(events, CLAIM_A)

    def test_passes_after_debt_cleared_and_survived(self):
        """Promote succeeds when debt is confirmed away and claim survived."""
        bypass = _verdict("survive", CLAIM_A, debt=True, confirmed=True)
        confirm = _confirm(bypass.id)
        events = [bypass, confirm]
        # Should not raise.
        assert_can_promote(events, CLAIM_A)

    def test_passes_on_clean_survive(self):
        """Promote succeeds on a clean (no-debt) survived claim."""
        events = _grill_survive(CLAIM_A)
        assert_can_promote(events, CLAIM_A)

    def test_raises_ungrilled_on_unknown_claim(self):
        """Promote fails for a claim_id that has no events."""
        events = _grill_survive(CLAIM_A)
        with pytest.raises(UngrilledError):
            assert_can_promote(events, "claim-unknown")

    def test_per_claim_debt_scoping(self):
        """Debt on claim-A does not block promotion of clean claim-B."""
        claim_b = "claim-b"
        # claim-A has debt (bypass verdict, unconfirmed).
        bypass_a = _verdict("survive", CLAIM_A, debt=True, confirmed=True)
        # claim-B survived cleanly.
        survive_b = _verdict("survive", claim_b, confirmed=True)
        events = [bypass_a, survive_b]
        # claim-B should be promotable despite claim-A's debt.
        assert_can_promote(events, claim_b)

    def test_debt_not_cleared_by_retracted_confirm(self):
        """If the CONFIRM targeting a debt event is itself retracted,
        the debt is still unresolved."""
        bypass = _verdict("survive", CLAIM_A, debt=True, confirmed=True)
        confirm = _confirm(bypass.id)
        retract_confirm = _retract(confirm.id)
        events = [bypass, confirm, retract_confirm]
        with pytest.raises(DebtBlockError):
            assert_can_promote(events, CLAIM_A)


# ===========================================================================
# assert_claim_no_debt
# ===========================================================================


class TestAssertClaimNoDebt:
    def test_raises_on_unresolved_debt(self):
        """Referencing a debt-bearing claim is hard-blocked."""
        bypass = _verdict("survive", CLAIM_A, debt=True, confirmed=True)
        events = [bypass]
        with pytest.raises(DebtBlockError):
            assert_claim_no_debt(events, CLAIM_A)

    def test_passes_on_clean_claim(self):
        """No error when claim has no debt events."""
        events = _grill_survive(CLAIM_A)
        assert_claim_no_debt(events, CLAIM_A)

    def test_passes_after_debt_confirmed(self):
        """Debt is resolved after a CONFIRM event targets it."""
        bypass = _verdict("survive", CLAIM_A, debt=True, confirmed=True)
        confirm = _confirm(bypass.id)
        events = [bypass, confirm]
        assert_claim_no_debt(events, CLAIM_A)

    def test_passes_on_unknown_claim(self):
        """No error when claim_id simply has no debt events."""
        events = _grill_survive(CLAIM_A)
        assert_claim_no_debt(events, "claim-nonexistent")


# ===========================================================================
# assert_park_isolation
# ===========================================================================


class TestAssertParkIsolation:
    def test_raises_on_parked_only_artifact(self):
        """A parked-only artifact cannot be fed to Lens or promoted."""
        park = make_event(type=PARK, actor="user", confirmed=True)
        events = [park]
        with pytest.raises(ParkIsolationViolation):
            assert_park_isolation(events)

    def test_passes_on_grilled_artifact(self):
        """Artifact that has been grilled is no longer in isolation."""
        park = make_event(type=PARK, actor="user", confirmed=True)
        events = [park] + _grill_survive(CLAIM_A)
        # Should not raise.
        assert_park_isolation(events)

    def test_passes_on_empty_events(self):
        """No events — not parked, so no isolation violation."""
        assert_park_isolation([])
