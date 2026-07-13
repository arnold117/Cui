"""Pure projection functions over event streams.

Spec §3.3: all derived views are computed from the event list.
No side effects, no state, no I/O.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from anneal.domain.constants import GROUND_NOT_SUPPORTED, GROUND_VERDICTS
from anneal.domain.events import (
    ANSWER,
    CHALLENGE,
    CONFIRM,
    EDIT,
    GROUND,
    PARK,
    RETRACT,
    VERDICT,
    Event,
)

# Grill event types — their presence means the artifact has been grilled.
GRILL_TYPES = {CHALLENGE, ANSWER, VERDICT}


def retracted_event_ids(events: list[Event]) -> set[str]:
    """Set of event IDs that have been retracted."""
    return {
        e.target_ref
        for e in events
        if e.type == RETRACT and e.target_ref is not None
    }


def _confirmed_event_ids(events: list[Event]) -> set[str]:
    """Set of event IDs that have been confirmed.

    A CONFIRM event whose own ID has been retracted does NOT count
    as a valid confirmation (Fix 6).
    """
    retracted = {
        e.target_ref
        for e in events
        if e.type == RETRACT and e.target_ref is not None
    }
    return {
        e.target_ref
        for e in events
        if e.type == CONFIRM and e.target_ref is not None and e.id not in retracted
    }


def has_grill_events(events: list[Event]) -> bool:
    """True if the event list contains any grill events."""
    return any(e.type in GRILL_TYPES for e in events)


def _survived_claim_ids(events: list[Event]) -> set[str]:
    """Claim IDs whose *last non-retracted confirmed* verdict is survive.

    A verdict counts only if it is confirmed (e.confirmed==True OR a
    non-retracted CONFIRM event targets it).
    """
    retracted = retracted_event_ids(events)
    confirmed = _confirmed_event_ids(events)
    # Walk in order; last non-retracted confirmed verdict wins.
    last_verdict: dict[str, str] = {}
    for e in events:
        if (
            e.type == VERDICT
            and e.id not in retracted
            and e.target_ref is not None
            and (e.confirmed or e.id in confirmed)
        ):
            last_verdict[e.target_ref] = e.payload.get("outcome", "")
    return {cid for cid, outcome in last_verdict.items() if outcome == "survive"}


def _killed_claim_ids(events: list[Event]) -> set[str]:
    """Claim IDs whose last non-retracted confirmed verdict is kill.

    A verdict counts only if it is confirmed (e.confirmed==True OR a
    non-retracted CONFIRM event targets it).
    """
    retracted = retracted_event_ids(events)
    confirmed = _confirmed_event_ids(events)
    last_verdict: dict[str, str] = {}
    for e in events:
        if (
            e.type == VERDICT
            and e.id not in retracted
            and e.target_ref is not None
            and (e.confirmed or e.id in confirmed)
        ):
            last_verdict[e.target_ref] = e.payload.get("outcome", "")
    return {cid for cid, outcome in last_verdict.items() if outcome == "kill"}


def ground_stance(payload: dict) -> str | None:
    """Resolve a GROUND payload's stance toward its claim (pure read).

    Returns one of:
    - ``"supports"`` / ``"contradicts"`` / ``"silent"`` — new three-state
      events (``payload["verdict"]``), plus legacy ``supported: True`` which
      reads as supports.
    - ``"not_supported"`` — legacy ``supported: False`` (未分态). Whether the
      paper was silent or contradicting was never recorded; we NEVER guess —
      projections/UI render the unclassified state as-is.
    - ``None`` — the payload carries neither field (malformed/foreign); the
      caller decides how to skip it. Read side never raises on legacy data.
    """
    verdict = payload.get("verdict")
    if verdict in GROUND_VERDICTS:
        return verdict
    if "supported" in payload:
        return "supports" if payload["supported"] else GROUND_NOT_SUPPORTED
    return None


def confirmed_ground_evidence(events: list[Event], claim_id: str) -> list[Event]:
    """Confirmed, non-retracted GROUND events targeting ``claim_id``.

    Completes P1's "观点对辩 → 证据对辩": confirmed literature-grounding
    evidence becomes a first-class input the grill can reason over.

    A GROUND event counts only if it is CONFIRMED (raw ``confirmed`` flag OR a
    non-retracted CONFIRM event targets it — the append-only confirm flow
    leaves the ground event's own flag False) and NOT itself retracted.
    Preserves ts order.
    """
    # Defensive sort (Fix 7).
    events = sorted(events, key=lambda e: e.ts)
    retracted = retracted_event_ids(events)
    confirmed = _confirmed_event_ids(events)
    return [
        e
        for e in events
        if e.type == GROUND
        and e.target_ref == claim_id
        and e.id not in retracted
        and (e.confirmed or e.id in confirmed)
    ]


def doc_projection(events: list[Event]) -> list[Event]:
    """Spec §3.3: doc = project(events: survive AND NOT debt AND confirmed).

    Returns filtered events suitable for DOC rendering.

    Rules:
    - Include events related to survived claims
      (verdict with outcome=survive targeting a claim).
    - Exclude events with debt=True.
    - Exclude events with confirmed=False.
    - Exclude events that have been retracted (a RETRACT event targets them).
    - Exclude verdict events with outcome=kill.
    - Exclude PARK events (park is isolation, not doc).
    - Exclude CONFIRM / RETRACT meta-events (bookkeeping, not content).
    - Exclude events whose target_ref points to a killed claim (Fix 4).
    """
    # Defensive sort — projections don't break on unsorted input (Fix 7).
    events = sorted(events, key=lambda e: e.ts)

    retracted = retracted_event_ids(events)
    survived = _survived_claim_ids(events)
    killed = _killed_claim_ids(events)
    confirmed = _confirmed_event_ids(events)

    result: list[Event] = []
    for e in events:
        # Skip meta-events.
        if e.type in {CONFIRM, RETRACT}:
            continue
        # Skip park events.
        if e.type == PARK:
            continue
        # Skip retracted events.
        if e.id in retracted:
            continue
        # Skip debt-bearing events.
        if e.debt:
            continue
        # Skip unconfirmed events. An event counts as confirmed if its own
        # flag is set OR a non-retracted CONFIRM event targets it — the
        # append-only confirm flow leaves the original event's flag False
        # (mirrors lens_feed Fix 5 / claim_status Fix H1).
        if not e.confirmed and e.id not in confirmed:
            continue
        # Skip kill verdicts.
        if e.type == VERDICT and e.payload.get("outcome") == "kill":
            continue
        # For verdict events, only include those whose claim survived.
        if e.type == VERDICT:
            if e.target_ref not in survived:
                continue
        # Skip events targeting a killed claim (Fix 4).
        if e.target_ref is not None and e.target_ref in killed:
            continue
        result.append(e)
    return result


def lens_feed_projection(events: list[Event]) -> list[Event]:
    """Spec §3.3: lens_feed = project(events: grilled AND scope != "surface").

    Rules:
    - Include events from grilled artifacts (has at least one CHALLENGE event).
    - Include BOTH survived and killed verdict events
      (killed = mining material for Lens).
    - Include challenge, answer, verdict, ground events.
    - Exclude EDIT events with scope="surface".
    - Include EDIT events with scope="substance".
    - Exclude PARK-only artifacts (no grill events = nothing to feed).
    - Exclude CONFIRM/RETRACT meta-events (bookkeeping, not content).
    - Only include confirmed events (Fix 5).
    """
    # Defensive sort (Fix 7).
    events = sorted(events, key=lambda e: e.ts)

    # If the artifact was never grilled, nothing to feed.
    if not has_grill_events(events):
        return []

    retracted = retracted_event_ids(events)
    confirmed = _confirmed_event_ids(events)
    result: list[Event] = []
    for e in events:
        # Skip retracted events.
        if e.id in retracted:
            continue
        # Skip meta-events.
        if e.type in {CONFIRM, RETRACT}:
            continue
        # Skip park events (park is isolation, not Lens food).
        if e.type == PARK:
            continue
        # Only include confirmed events (Fix 5):
        # confirmed=True on the event itself, OR a CONFIRM event targets it.
        if not e.confirmed and e.id not in confirmed:
            continue
        # Edit events: include substance, exclude surface.
        if e.type == EDIT:
            if e.payload.get("scope") == "surface":
                continue
        result.append(e)
    return result


def claim_status(events: list[Event], claim_id: str) -> str:
    """Derive claim status from events.

    Returns: "open" | "survived" | "killed" | "parked"

    Logic:
    - If a VERDICT with outcome="survive" exists (last non-retracted
      *confirmed* verdict wins) -> "survived"
    - If a VERDICT with outcome="kill" exists (same rule) -> "killed"
    - If only a PARK event exists targeting this claim -> "parked"
    - Otherwise -> "open"
    - Retracted verdicts don't count.
    - Unconfirmed verdicts don't count (Fix H1).
    """
    # Defensive sort (Fix 7).
    events = sorted(events, key=lambda e: e.ts)
    retracted = retracted_event_ids(events)
    confirmed = _confirmed_event_ids(events)

    last_outcome: str | None = None
    has_park = False

    for e in events:
        if e.target_ref != claim_id:
            continue
        if e.id in retracted:
            continue
        if e.type == VERDICT:
            # Only count confirmed verdicts (Fix H1).
            if e.confirmed or e.id in confirmed:
                last_outcome = e.payload.get("outcome")
        elif e.type == PARK:
            has_park = True

    if last_outcome == "survive":
        return "survived"
    if last_outcome == "kill":
        return "killed"
    if has_park and last_outcome is None:
        return "parked"
    return "open"


class VerdictPrecedent(BaseModel):
    """The 判例 a claim's ruling verdict left behind (死因分诊 read side).

    ``outcome`` uses the raw verdict payload vocabulary ("survive"/"kill").
    ``death_cause`` is None for survive verdicts AND for legacy kill verdicts
    recorded before death-cause triage — projection semantics: unclassified
    (死因未分类). Legacy events never break; every field is read with .get.
    """

    outcome: str
    death_cause: str | None = None
    rationale: str = ""
    revival_condition: str | None = None
    successor_claim_id: str | None = None


def verdict_precedent(events: list[Event], claim_id: str) -> VerdictPrecedent | None:
    """Precedent of the claim's ruling verdict, or None without one.

    Selection rule mirrors ``claim_status``: the LAST non-retracted CONFIRMED
    verdict targeting ``claim_id`` wins (unconfirmed drafts and retracted
    verdicts never count — the confirm gate is the trust chain, so an injected
    rationale is always human-written or human-signed).
    """
    # Defensive sort (Fix 7).
    events = sorted(events, key=lambda e: e.ts)
    retracted = retracted_event_ids(events)
    confirmed = _confirmed_event_ids(events)

    ruling: Event | None = None
    for e in events:
        if e.type != VERDICT or e.target_ref != claim_id:
            continue
        if e.id in retracted:
            continue
        if e.confirmed or e.id in confirmed:
            ruling = e

    if ruling is None:
        return None
    p = ruling.payload
    return VerdictPrecedent(
        outcome=p.get("outcome", ""),
        death_cause=p.get("death_cause"),
        rationale=p.get("rationale", "") or "",
        revival_condition=p.get("revival_condition"),
        successor_claim_id=p.get("successor_claim_id"),
    )


def has_unresolved_debt(events: list[Event]) -> bool:
    """True if any event has debt=True and no subsequent CONFIRM event targets it."""
    # Defensive sort (Fix 7).
    events = sorted(events, key=lambda e: e.ts)
    confirmed = _confirmed_event_ids(events)
    return any(e.debt and e.id not in confirmed for e in events)


def pending_events(events: list[Event]) -> list[Event]:
    """Events where confirmed=False and no CONFIRM or RETRACT event targets them."""
    # Defensive sort (Fix 7).
    events = sorted(events, key=lambda e: e.ts)
    confirmed = _confirmed_event_ids(events)
    retracted = retracted_event_ids(events)
    resolved = confirmed | retracted
    return [
        e
        for e in events
        if not e.confirmed
        and e.id not in resolved
        and e.type not in {CONFIRM, RETRACT}
    ]


def is_parked(events: list[Event]) -> bool:
    """True if artifact has only park events and no grill events (challenge/answer/verdict)."""
    # Defensive sort (Fix 7).
    events = sorted(events, key=lambda e: e.ts)
    has_park = any(e.type == PARK for e in events)
    return has_park and not has_grill_events(events)


class DocVersion(BaseModel):
    """A snapshot of the DOC, emitted whenever its content actually changes.

    The DOC content at any point is defined by doc_projection(...) run over the
    prefix of events up to and including the triggering event. A new version is
    emitted only when that projected content (the set of event IDs) differs from
    the previously emitted version.
    """

    version: int
    ts: datetime
    triggering_event_id: str
    triggering_event_type: str
    doc: list[Event]
    added_event_ids: list[str] = Field(default_factory=list)
    removed_event_ids: list[str] = Field(default_factory=list)


def snapshot_projection(events: list[Event]) -> list[DocVersion]:
    """Spec §3.3: DOC version history derived from event prefixes.

    A "version" is a snapshot of the DOC. A new version is emitted whenever the
    DOC content actually changes — i.e. whenever the SET of event IDs returned
    by doc_projection over the prefix events[0..i] differs from the previously
    emitted version's id-set.

    - Walk events in ts order, growing a prefix one event at a time.
    - For each prefix, compute doc_projection(prefix) and diff its id-set
      against the previously emitted id-set (baseline = empty set).
    - On a difference, emit a DocVersion with a 1-based sequential `version`,
      the triggering event's ts/id/type, the full doc snapshot, and the
      added/removed event ids (in doc order for added).
    - No leading empty version (baseline is empty), but a transition BACK to an
      empty doc (e.g. everything retracted) IS a real change and emits.
    - Event types are never special-cased; only doc_projection outputs are
      diffed — promote, confirmed survive verdicts, substance edits, retracts,
      and CONFIRM meta-events that flip in-doc content all surface naturally.
    """
    # Defensive sort (Fix 7).
    events = sorted(events, key=lambda e: e.ts)

    versions: list[DocVersion] = []
    prev_doc: list[Event] = []
    prev_ids: set[str] = set()
    counter = 0

    for i in range(len(events)):
        prefix = events[: i + 1]
        current = doc_projection(prefix)
        current_ids = {e.id for e in current}

        if current_ids == prev_ids:
            continue

        counter += 1
        trigger = events[i]
        # added in current-doc order; removed in prior-doc order — both
        # deterministic and meaningful (no set-iteration ordering).
        added = [e.id for e in current if e.id not in prev_ids]
        removed = [e.id for e in prev_doc if e.id not in current_ids]
        versions.append(
            DocVersion(
                version=counter,
                ts=trigger.ts,
                triggering_event_id=trigger.id,
                triggering_event_type=trigger.type,
                doc=current,
                added_event_ids=added,
                removed_event_ids=removed,
            )
        )
        prev_doc = current
        prev_ids = current_ids

    return versions
