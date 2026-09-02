"""Business-rule invariants checked before state transitions.

Pure functions that take an event list and raise on violation.
They delegate to projections.py for derived state — no reimplementation.
"""

from __future__ import annotations

from cui.domain.events import Event
from cui.domain.projections import (
    _confirmed_event_ids,
    _killed_claim_ids,
    _survived_claim_ids,
    is_parked,
    retracted_event_ids,
)


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class DebtBlockError(Exception):
    """Raised when unresolved debt blocks an operation."""


class UngrilledError(Exception):
    """Raised when a claim hasn't survived grill."""


class KilledClaimError(Exception):
    """Raised when a claim has been killed."""


class ParkIsolationViolation(Exception):
    """Raised when park isolation is breached."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _claim_has_unresolved_debt(events: list[Event], claim_id: str) -> bool:
    """True if *any* event targeting this claim has debt=True and hasn't been confirmed.

    "Targeting" means: event.target_ref == claim_id, OR the event itself is a
    debt-bearing VERDICT whose target_ref is the claim.  We also need to catch
    debt-bearing events that *are* the claim (e.g. a bypass verdict that has
    debt=True and target_ref=claim_id).

    A debt event is resolved when a CONFIRM event targets it (and that CONFIRM
    has not itself been retracted).
    """
    confirmed = _confirmed_event_ids(events)
    for e in events:
        if e.debt and e.target_ref == claim_id and e.id not in confirmed:
            return True
    return False


# ---------------------------------------------------------------------------
# Invariant assertions
# ---------------------------------------------------------------------------


def assert_can_promote(events: list[Event], claim_id: str) -> None:
    """Hard-block promote if:

    1. Claim is killed -> KilledClaimError
    2. Claim hasn't survived grill (no verdict=survive) -> UngrilledError
    3. Claim has unresolved debt -> DebtBlockError

    Spec §4 Q-D + §5 acceptance criterion 7.
    """
    # Check killed first — a killed claim can never be promoted regardless.
    if claim_id in _killed_claim_ids(events):
        raise KilledClaimError(
            f"Claim {claim_id!r} has been killed and cannot be promoted"
        )

    # Must have survived grill.
    if claim_id not in _survived_claim_ids(events):
        raise UngrilledError(
            f"Claim {claim_id!r} has not survived grill"
        )

    # Debt gate.
    if _claim_has_unresolved_debt(events, claim_id):
        raise DebtBlockError(
            f"Claim {claim_id!r} has unresolved debt — clear it before promoting"
        )


def assert_claim_no_debt(events: list[Event], claim_id: str) -> None:
    """Hard-block referencing a claim that carries unresolved debt.

    Spec §4 Q-D: third hard-block trigger (promote/export/reference).
    """
    if _claim_has_unresolved_debt(events, claim_id):
        raise DebtBlockError(
            f"Claim {claim_id!r} has unresolved debt — cannot reference"
        )


def assert_park_isolation(events: list[Event]) -> None:
    """Ensures parked-only artifacts cannot be fed to Lens or promoted.

    PARK = sealed isolation zone. The only path to the moat is through GRILL.
    """
    if is_parked(events):
        raise ParkIsolationViolation(
            "Artifact is still in PARK isolation — grill it first"
        )
