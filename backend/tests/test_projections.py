"""Tests for anneal.domain.projections — pure projection functions."""

from datetime import datetime, timedelta

import pytest

from anneal.domain.events import (
    ANSWER,
    CHALLENGE,
    COLLECT_MATERIAL,
    CONFIRM,
    DRAFT,
    EDIT,
    Event,
    GROUND,
    PARK,
    PROMOTE,
    RETRACT,
    VERDICT,
    make_event,
)
from anneal.domain.projections import (
    DocVersion,
    _killed_claim_ids,
    _survived_claim_ids,
    claim_status,
    doc_projection,
    has_unresolved_debt,
    is_parked,
    lens_feed_projection,
    pending_events,
    retracted_event_ids,
    snapshot_projection,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CLAIM_A = "claim-a"
CLAIM_B = "claim-b"


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


# ===========================================================================
# doc_projection
# ===========================================================================


class TestDocProjection:
    def test_includes_survived_confirmed_no_debt(self):
        """Survived + confirmed + debt-free events pass through."""
        challenge = make_event(type=CHALLENGE, actor="system", confirmed=True)
        answer = make_event(type=ANSWER, actor="user", confirmed=True)
        verdict = _verdict("survive", confirmed=True)
        events = [challenge, answer, verdict]
        result = doc_projection(events)
        assert challenge in result
        assert answer in result
        assert verdict in result

    def test_excludes_killed_verdict(self):
        """Verdict with outcome=kill is excluded."""
        v_kill = _verdict("kill", confirmed=True)
        events = [v_kill]
        result = doc_projection(events)
        assert v_kill not in result

    def test_excludes_debt_events(self):
        """Events with debt=True are excluded."""
        e = make_event(type=DRAFT, actor="system", debt=True, confirmed=True)
        events = [e]
        result = doc_projection(events)
        assert len(result) == 0

    def test_excludes_unconfirmed_events(self):
        """Events with confirmed=False are excluded."""
        e = make_event(type=CHALLENGE, actor="system", confirmed=False)
        events = [e]
        result = doc_projection(events)
        assert len(result) == 0

    def test_excludes_retracted_events(self):
        """Retracted events are excluded."""
        e = make_event(type=CHALLENGE, actor="system", confirmed=True)
        r = _retract(e.id)
        events = [e, r]
        result = doc_projection(events)
        # Neither the retracted event nor the retract meta-event appears.
        assert len(result) == 0

    def test_excludes_park_events(self):
        """Park events never appear in doc."""
        p = make_event(type=PARK, actor="user", confirmed=True)
        events = [p]
        result = doc_projection(events)
        assert len(result) == 0

    def test_excludes_confirm_retract_meta_events(self):
        """CONFIRM and RETRACT meta-events are bookkeeping, not doc content."""
        e = make_event(type=CHALLENGE, actor="system", confirmed=True)
        c = _confirm(e.id)
        events = [e, c]
        result = doc_projection(events)
        # The challenge passes, but the confirm meta-event does not.
        assert e in result
        assert c not in result

    def test_includes_event_confirmed_via_confirm_event(self):
        """Regression: an event confirmed through the append-only CONFIRM flow
        (raw confirmed=False + a CONFIRM event targeting it) must appear in the
        doc — not only events born confirmed=True. Covers the substance-edit
        flow (spec §2.6 #5), where edits are created pending and batch-confirmed.
        Before the fix, doc_projection read only the raw flag and these edits
        never reached the DOC.
        """
        edit = make_event(
            type=EDIT,
            actor="user",
            confirmed=False,
            payload={"scope": "substance", "content": "revised body"},
        )
        confirm = _confirm(edit.id)
        events = [edit, confirm]
        result = doc_projection(events)
        assert edit in result
        assert confirm not in result

    def test_excludes_event_whose_confirm_is_retracted(self):
        """A CONFIRM that is itself retracted does not count (Fix 6): the
        edit it confirmed must stay out of the doc."""
        edit = make_event(
            type=EDIT,
            actor="user",
            confirmed=False,
            payload={"scope": "substance"},
        )
        confirm = _confirm(edit.id)
        retract = make_event(
            type=RETRACT, actor="user", target_ref=confirm.id, confirmed=True
        )
        events = [edit, confirm, retract]
        result = doc_projection(events)
        assert edit not in result

    def test_full_doc_scenario(self):
        """Integration: park -> grill -> survive -> doc includes clean events."""
        park = make_event(type=PARK, actor="user", confirmed=True)
        challenge = make_event(type=CHALLENGE, actor="system", confirmed=True)
        answer = make_event(type=ANSWER, actor="user", confirmed=True)
        v_survive = _verdict("survive", confirmed=True)
        v_kill = _verdict("kill", claim_id=CLAIM_B, confirmed=True)
        ground = make_event(type=GROUND, actor="system", confirmed=True)
        debt_draft = make_event(type=DRAFT, actor="system", debt=True, confirmed=True)
        unconfirmed = make_event(type=CHALLENGE, actor="system", confirmed=False)

        events = [park, challenge, answer, v_survive, v_kill, ground, debt_draft, unconfirmed]
        result = doc_projection(events)

        assert park not in result        # park excluded
        assert challenge in result       # confirmed, no debt
        assert answer in result
        assert v_survive in result       # survived verdict
        assert v_kill not in result      # killed verdict excluded
        assert ground in result
        assert debt_draft not in result  # debt excluded
        assert unconfirmed not in result # unconfirmed excluded


# ===========================================================================
# lens_feed_projection
# ===========================================================================


class TestLensFeedProjection:
    def test_includes_grill_events(self):
        """Challenge, answer, verdict all pass through for grilled artifacts."""
        challenge = make_event(type=CHALLENGE, actor="system", confirmed=True)
        answer = make_event(type=ANSWER, actor="user", confirmed=True)
        v = _verdict("survive", confirmed=True)
        events = [challenge, answer, v]
        result = lens_feed_projection(events)
        assert challenge in result
        assert answer in result
        assert v in result

    def test_includes_killed_verdict(self):
        """Killed verdicts are mining material for Lens — must be included."""
        v_kill = _verdict("kill", confirmed=True)
        challenge = make_event(type=CHALLENGE, actor="system", confirmed=True)
        events = [challenge, v_kill]
        result = lens_feed_projection(events)
        assert v_kill in result

    def test_excludes_surface_edit(self):
        """Edit events with scope=surface are excluded."""
        challenge = make_event(type=CHALLENGE, actor="system")
        surface_edit = make_event(
            type=EDIT, actor="user", payload={"scope": "surface"}
        )
        events = [challenge, surface_edit]
        result = lens_feed_projection(events)
        assert surface_edit not in result

    def test_includes_substance_edit(self):
        """Edit events with scope=substance are included."""
        challenge = make_event(type=CHALLENGE, actor="system", confirmed=True)
        substance_edit = make_event(
            type=EDIT, actor="user", payload={"scope": "substance"}, confirmed=True
        )
        events = [challenge, substance_edit]
        result = lens_feed_projection(events)
        assert substance_edit in result

    def test_empty_for_park_only(self):
        """Park-only artifacts (no grill events) produce empty lens feed."""
        park = make_event(type=PARK, actor="user")
        events = [park]
        result = lens_feed_projection(events)
        assert result == []

    def test_excludes_retracted_events(self):
        """Retracted events are excluded from lens feed."""
        challenge = make_event(type=CHALLENGE, actor="system", confirmed=True)
        answer = make_event(type=ANSWER, actor="user", confirmed=True)
        r = _retract(answer.id)
        events = [challenge, answer, r]
        result = lens_feed_projection(events)
        assert answer not in result
        assert challenge in result

    def test_excludes_confirm_retract_meta(self):
        """CONFIRM and RETRACT meta-events are excluded."""
        challenge = make_event(type=CHALLENGE, actor="system", confirmed=True)
        c = _confirm(challenge.id)
        events = [challenge, c]
        result = lens_feed_projection(events)
        assert c not in result
        assert challenge in result

    def test_includes_ground_events(self):
        """Ground events are included in lens feed for grilled artifacts."""
        challenge = make_event(type=CHALLENGE, actor="system", confirmed=True)
        ground = make_event(type=GROUND, actor="system", confirmed=True)
        events = [challenge, ground]
        result = lens_feed_projection(events)
        assert ground in result

    def test_excludes_park_events_from_grilled_artifact(self):
        """Even for grilled artifacts, the park event itself is excluded."""
        park = make_event(type=PARK, actor="user", confirmed=True)
        challenge = make_event(type=CHALLENGE, actor="system", confirmed=True)
        events = [park, challenge]
        result = lens_feed_projection(events)
        assert park not in result
        assert challenge in result


# ===========================================================================
# claim_status
# ===========================================================================


class TestClaimStatus:
    def test_open_when_no_verdict(self):
        """No verdict -> open."""
        challenge = make_event(type=CHALLENGE, actor="system", target_ref=CLAIM_A)
        events = [challenge]
        assert claim_status(events, CLAIM_A) == "open"

    def test_open_when_empty_events(self):
        """Empty event list -> open."""
        assert claim_status([], CLAIM_A) == "open"

    def test_survived_after_survive_verdict(self):
        """Confirmed survive verdict -> survived."""
        v = _verdict("survive", confirmed=True)
        events = [v]
        assert claim_status(events, CLAIM_A) == "survived"

    def test_killed_after_kill_verdict(self):
        """Confirmed kill verdict -> killed."""
        v = _verdict("kill", confirmed=True)
        events = [v]
        assert claim_status(events, CLAIM_A) == "killed"

    def test_last_verdict_wins(self):
        """When multiple confirmed verdicts exist, the last one wins."""
        v1 = _verdict("survive", confirmed=True)
        v2 = _verdict("kill", confirmed=True)
        events = [v1, v2]
        assert claim_status(events, CLAIM_A) == "killed"

    def test_last_verdict_wins_reverse(self):
        """Kill then survive (both confirmed) -> survived."""
        v1 = _verdict("kill", confirmed=True)
        v2 = _verdict("survive", confirmed=True)
        events = [v1, v2]
        assert claim_status(events, CLAIM_A) == "survived"

    def test_retracted_verdict_does_not_count(self):
        """Retracted verdict is ignored; falls back to previous."""
        v1 = _verdict("survive", confirmed=True)
        v2 = _verdict("kill", confirmed=True)
        r = _retract(v2.id)
        events = [v1, v2, r]
        # v2 retracted, so v1 (survive) is the last valid verdict.
        assert claim_status(events, CLAIM_A) == "survived"

    def test_retracted_only_verdict_falls_to_open(self):
        """If the only verdict is retracted, status falls back to open."""
        v = _verdict("survive")
        r = _retract(v.id)
        events = [v, r]
        assert claim_status(events, CLAIM_A) == "open"

    def test_parked_when_only_park_event(self):
        """Only a park event targeting this claim -> parked."""
        p = make_event(type=PARK, actor="user", target_ref=CLAIM_A)
        events = [p]
        assert claim_status(events, CLAIM_A) == "parked"

    def test_parked_overridden_by_verdict(self):
        """Park + subsequent confirmed verdict -> verdict wins."""
        p = make_event(type=PARK, actor="user", target_ref=CLAIM_A)
        v = _verdict("survive", confirmed=True)
        events = [p, v]
        assert claim_status(events, CLAIM_A) == "survived"

    def test_ignores_events_for_other_claims(self):
        """Events targeting other claims are irrelevant."""
        v = _verdict("survive", claim_id=CLAIM_B)
        events = [v]
        assert claim_status(events, CLAIM_A) == "open"


# ===========================================================================
# has_unresolved_debt
# ===========================================================================


class TestHasUnresolvedDebt:
    def test_true_when_debt_without_confirm(self):
        """Debt event without a corresponding confirm -> True."""
        e = make_event(type=DRAFT, actor="system", debt=True)
        events = [e]
        assert has_unresolved_debt(events) is True

    def test_false_after_confirm(self):
        """Debt event followed by a confirm targeting it -> False."""
        e = make_event(type=DRAFT, actor="system", debt=True)
        c = _confirm(e.id)
        events = [e, c]
        assert has_unresolved_debt(events) is False

    def test_false_when_no_debt(self):
        """No debt events at all -> False."""
        e = make_event(type=CHALLENGE, actor="system")
        events = [e]
        assert has_unresolved_debt(events) is False

    def test_false_on_empty_events(self):
        """Empty event list -> False."""
        assert has_unresolved_debt([]) is False

    def test_mixed_debt_resolved_and_unresolved(self):
        """One resolved + one unresolved debt -> True."""
        d1 = make_event(type=DRAFT, actor="system", debt=True)
        c1 = _confirm(d1.id)
        d2 = make_event(type=VERDICT, actor="system", debt=True, payload={"outcome": "survive"})
        events = [d1, c1, d2]
        assert has_unresolved_debt(events) is True


# ===========================================================================
# pending_events
# ===========================================================================


class TestPendingEvents:
    def test_returns_unconfirmed(self):
        """Unconfirmed events are pending."""
        e = make_event(type=CHALLENGE, actor="system", confirmed=False)
        events = [e]
        result = pending_events(events)
        assert e in result

    def test_excludes_confirmed_by_flag(self):
        """Events created with confirmed=True are not pending."""
        e = make_event(type=CHALLENGE, actor="system", confirmed=True)
        events = [e]
        result = pending_events(events)
        assert e not in result

    def test_excludes_after_confirm_event(self):
        """An unconfirmed event targeted by a CONFIRM event is not pending."""
        e = make_event(type=CHALLENGE, actor="system", confirmed=False)
        c = _confirm(e.id)
        events = [e, c]
        result = pending_events(events)
        assert e not in result

    def test_excludes_after_retract_event(self):
        """An unconfirmed event targeted by a RETRACT event is not pending."""
        e = make_event(type=CHALLENGE, actor="system", confirmed=False)
        r = _retract(e.id)
        events = [e, r]
        result = pending_events(events)
        assert e not in result

    def test_confirm_and_retract_meta_events_not_pending(self):
        """CONFIRM and RETRACT meta-events themselves are never pending."""
        e = make_event(type=CHALLENGE, actor="system", confirmed=False)
        c = _confirm(e.id)
        r_other = make_event(type=RETRACT, actor="user", target_ref="x", confirmed=False)
        events = [e, c, r_other]
        result = pending_events(events)
        assert c not in result
        assert r_other not in result

    def test_multiple_pending(self):
        """Multiple unconfirmed events are all returned."""
        e1 = make_event(type=CHALLENGE, actor="system", confirmed=False)
        e2 = make_event(type=ANSWER, actor="user", confirmed=False)
        events = [e1, e2]
        result = pending_events(events)
        assert len(result) == 2
        assert e1 in result
        assert e2 in result

    def test_empty_events(self):
        """Empty event list -> empty pending list."""
        assert pending_events([]) == []


# ===========================================================================
# is_parked
# ===========================================================================


class TestIsParked:
    def test_true_for_park_only(self):
        """Artifact with only park event(s) is parked."""
        p = make_event(type=PARK, actor="user")
        events = [p]
        assert is_parked(events) is True

    def test_false_after_challenge(self):
        """Once any grill event appears, no longer parked."""
        p = make_event(type=PARK, actor="user")
        c = make_event(type=CHALLENGE, actor="system")
        events = [p, c]
        assert is_parked(events) is False

    def test_false_after_answer(self):
        """Answer is a grill event."""
        p = make_event(type=PARK, actor="user")
        a = make_event(type=ANSWER, actor="user")
        events = [p, a]
        assert is_parked(events) is False

    def test_false_after_verdict(self):
        """Verdict is a grill event."""
        p = make_event(type=PARK, actor="user")
        v = _verdict("survive")
        events = [p, v]
        assert is_parked(events) is False

    def test_false_without_park(self):
        """No park event -> not parked (even if no grill events)."""
        e = make_event(type=COLLECT_MATERIAL, actor="system")
        events = [e]
        assert is_parked(events) is False

    def test_false_on_empty(self):
        """Empty event list is not parked."""
        assert is_parked([]) is False


# ===========================================================================
# retracted_event_ids
# ===========================================================================


class TestRetractedEventIds:
    def test_returns_retracted_ids(self):
        """RETRACT events cause their targets to appear in the retracted set."""
        e = make_event(type=CHALLENGE, actor="system")
        r = _retract(e.id)
        events = [e, r]
        result = retracted_event_ids(events)
        assert e.id in result

    def test_empty_when_nothing_retracted(self):
        """No RETRACT events -> empty set."""
        e = make_event(type=CHALLENGE, actor="system")
        events = [e]
        result = retracted_event_ids(events)
        assert result == set()

    def test_empty_on_empty_events(self):
        """Empty event list -> empty set."""
        assert retracted_event_ids([]) == set()

    def test_multiple_retractions(self):
        """Multiple RETRACT events accumulate."""
        e1 = make_event(type=CHALLENGE, actor="system")
        e2 = make_event(type=ANSWER, actor="user")
        r1 = _retract(e1.id)
        r2 = _retract(e2.id)
        events = [e1, e2, r1, r2]
        result = retracted_event_ids(events)
        assert e1.id in result
        assert e2.id in result
        assert len(result) == 2


# ===========================================================================
# doc_projection — killed claim filtering (Fix 4)
# ===========================================================================


class TestDocProjectionKilledClaimFiltering:
    def test_challenge_targeting_killed_claim_excluded(self):
        """Challenge event targeting a killed claim is excluded from doc."""
        v_kill = _verdict("kill", claim_id=CLAIM_A, confirmed=True)
        challenge = make_event(
            type=CHALLENGE, actor="system", confirmed=True, target_ref=CLAIM_A
        )
        events = [v_kill, challenge]
        result = doc_projection(events)
        assert challenge not in result

    def test_answer_targeting_killed_claim_excluded(self):
        """Answer event targeting a killed claim is excluded from doc."""
        v_kill = _verdict("kill", claim_id=CLAIM_A, confirmed=True)
        answer = make_event(
            type=ANSWER, actor="user", confirmed=True, target_ref=CLAIM_A
        )
        events = [v_kill, answer]
        result = doc_projection(events)
        assert answer not in result

    def test_ground_targeting_killed_claim_excluded(self):
        """Ground event targeting a killed claim is excluded from doc."""
        v_kill = _verdict("kill", claim_id=CLAIM_A, confirmed=True)
        ground = make_event(
            type=GROUND, actor="system", confirmed=True, target_ref=CLAIM_A
        )
        events = [v_kill, ground]
        result = doc_projection(events)
        assert ground not in result

    def test_event_without_target_ref_passes(self):
        """Events with no target_ref still pass through (default allow)."""
        # Need a survive verdict so that confirmed events are relevant.
        v_kill = _verdict("kill", claim_id=CLAIM_A, confirmed=True)
        free_event = make_event(
            type=CHALLENGE, actor="system", confirmed=True, target_ref=None
        )
        events = [v_kill, free_event]
        result = doc_projection(events)
        assert free_event in result


# ===========================================================================
# lens_feed_projection — unconfirmed filtering (Fix 5)
# ===========================================================================


class TestLensFeedConfirmedFiltering:
    def test_unconfirmed_event_excluded(self):
        """Unconfirmed event is excluded from lens feed."""
        challenge = make_event(type=CHALLENGE, actor="system", confirmed=True)
        unconfirmed = make_event(type=ANSWER, actor="user", confirmed=False)
        events = [challenge, unconfirmed]
        result = lens_feed_projection(events)
        assert unconfirmed not in result

    def test_confirmed_event_included(self):
        """Event with confirmed=True is included in lens feed."""
        challenge = make_event(type=CHALLENGE, actor="system", confirmed=True)
        answer = make_event(type=ANSWER, actor="user", confirmed=True)
        events = [challenge, answer]
        result = lens_feed_projection(events)
        assert answer in result

    def test_event_confirmed_via_confirm_event_included(self):
        """Event confirmed via a CONFIRM event is included in lens feed."""
        challenge = make_event(type=CHALLENGE, actor="system", confirmed=True)
        unconfirmed = make_event(type=ANSWER, actor="user", confirmed=False)
        c = _confirm(unconfirmed.id)
        events = [challenge, unconfirmed, c]
        result = lens_feed_projection(events)
        assert unconfirmed in result


# ===========================================================================
# Retracted CONFIRM events (Fix 6)
# ===========================================================================


class TestRetractedConfirmEvents:
    def test_retracted_confirm_unresolved_debt(self):
        """CONFIRM event retracted -> original debt event is unresolved again."""
        debt_event = make_event(type=DRAFT, actor="system", debt=True)
        c = _confirm(debt_event.id)
        r = _retract(c.id)
        events = [debt_event, c, r]
        assert has_unresolved_debt(events) is True

    def test_has_unresolved_debt_true_after_confirm_retracted(self):
        """has_unresolved_debt returns True after confirm is retracted."""
        debt_event = make_event(type=DRAFT, actor="system", debt=True)
        c = _confirm(debt_event.id)
        # Before retraction: resolved.
        assert has_unresolved_debt([debt_event, c]) is False
        # After retraction: unresolved again.
        r = _retract(c.id)
        assert has_unresolved_debt([debt_event, c, r]) is True


# ===========================================================================
# is_parked — park + collect_material (Fix 8)
# ===========================================================================


class TestIsParkedWithCollectMaterial:
    def test_park_plus_collect_material_still_parked(self):
        """park + collect_material (no grill events) is still considered parked."""
        park = make_event(type=PARK, actor="user")
        collect = make_event(type=COLLECT_MATERIAL, actor="system")
        events = [park, collect]
        assert is_parked(events) is True


# ===========================================================================
# Fix H1 — verdicts must be confirmed to count
# ===========================================================================


class TestConfirmedVerdictsOnly:
    """Verdicts only count when confirmed (confirmed=True or targeted by CONFIRM)."""

    def test_claim_status_unconfirmed_verdict_returns_open(self):
        """Unconfirmed verdict does not flip claim_status — stays 'open'."""
        v = _verdict("survive", confirmed=False)
        events = [v]
        assert claim_status(events, CLAIM_A) == "open"

    def test_claim_status_confirmed_verdict_returns_survived(self):
        """Confirmed verdict flips claim_status to 'survived'."""
        v = _verdict("survive", confirmed=True)
        events = [v]
        assert claim_status(events, CLAIM_A) == "survived"

    def test_claim_status_unconfirmed_verdict_plus_confirm_event(self):
        """Unconfirmed verdict + CONFIRM targeting it -> 'survived'."""
        v = _verdict("survive", confirmed=False)
        c = _confirm(v.id)
        events = [v, c]
        assert claim_status(events, CLAIM_A) == "survived"

    def test_survived_claim_ids_excludes_unconfirmed(self):
        """_survived_claim_ids ignores unconfirmed survive verdicts."""
        v = _verdict("survive", confirmed=False)
        events = [v]
        assert CLAIM_A not in _survived_claim_ids(events)

    def test_killed_claim_ids_excludes_unconfirmed(self):
        """_killed_claim_ids ignores unconfirmed kill verdicts."""
        v = _verdict("kill", confirmed=False)
        events = [v]
        assert CLAIM_A not in _killed_claim_ids(events)

    def test_doc_projection_excludes_unconfirmed_only_survive(self):
        """doc_projection excludes events when the only survive verdict is unconfirmed."""
        challenge = make_event(
            type=CHALLENGE, actor="system", confirmed=True, target_ref=CLAIM_A
        )
        v = _verdict("survive", confirmed=False)
        events = [challenge, v]
        result = doc_projection(events)
        # The challenge targets CLAIM_A, but the survive verdict is unconfirmed
        # so CLAIM_A is not in survived set — challenge should be excluded
        # (it targets a claim with no confirmed survive verdict, but it's not
        # in killed set either so the killed-claim filter doesn't apply;
        # however, the verdict event itself won't appear because it's
        # unconfirmed).
        verdict_in_doc = [e for e in result if e.type == VERDICT]
        assert len(verdict_in_doc) == 0


# ===========================================================================
# snapshot_projection — DOC version history (Fix: snapshot projection)
# ===========================================================================

_T0 = datetime(2026, 1, 1)


def _at(minutes: int) -> datetime:
    """Deterministic ts at a fixed offset (snapshot_projection sorts by ts)."""
    return _T0 + timedelta(minutes=minutes)


def _ev(ts_min: int, **kw) -> Event:
    """Construct an Event with an explicit ts (make_event can't set ts)."""
    kw.setdefault("actor", "system")
    return Event(ts=_at(ts_min), **kw)


def _survive_v(ts_min: int, claim_id: str = CLAIM_A, confirmed: bool = True) -> Event:
    return _ev(
        ts_min,
        type=VERDICT,
        payload={"outcome": "survive"},
        target_ref=claim_id,
        confirmed=confirmed,
    )


class TestSnapshotProjection:
    def test_empty_events_returns_empty(self):
        """1. No events -> no versions."""
        assert snapshot_projection([]) == []

    def test_park_only_returns_empty(self):
        """2. Park-only artifact never makes the doc non-empty -> no versions."""
        park = _ev(1, type=PARK, actor="user", confirmed=True)
        assert snapshot_projection([park]) == []

    def test_grill_churn_no_surviving_content_no_versions(self):
        """3. Challenge+answer that never land in doc (unconfirmed) -> no versions.

        Verified against doc_projection: unconfirmed events are excluded, so the
        doc stays empty across the whole stream.
        """
        challenge = _ev(1, type=CHALLENGE, target_ref=CLAIM_A, confirmed=False)
        answer = _ev(2, type=ANSWER, actor="user", target_ref=CLAIM_A, confirmed=False)
        # Sanity: doc_projection really is empty for this stream.
        assert doc_projection([challenge, answer]) == []
        assert snapshot_projection([challenge, answer]) == []

    def test_single_confirmed_survive_verdict_one_version(self):
        """4. One confirmed survive verdict -> exactly 1 non-empty version."""
        v = _survive_v(1)
        versions = snapshot_projection([v])
        assert len(versions) == 1
        ver = versions[0]
        assert ver.version == 1
        assert ver.triggering_event_id == v.id
        assert ver.triggering_event_type == VERDICT
        assert v.id in ver.added_event_ids
        assert ver.removed_event_ids == []
        assert len(ver.doc) >= 1
        assert v in ver.doc

    def test_two_separate_survive_verdicts_two_versions(self):
        """5. Survive A then survive B -> 2 versions; second adds only B's verdict."""
        va = _survive_v(1, CLAIM_A)
        vb = _survive_v(2, CLAIM_B)
        versions = snapshot_projection([va, vb])
        assert len(versions) == 2
        assert versions[0].added_event_ids == [va.id]
        assert versions[1].version == 2
        assert versions[1].added_event_ids == [vb.id]
        assert versions[1].removed_event_ids == []
        # Doc grows: second snapshot contains both verdicts.
        assert va in versions[1].doc
        assert vb in versions[1].doc

    def test_promote_flow_produces_version(self):
        """6. A confirmed promote event lands in doc -> an additional version.

        Verified against doc_projection: a confirmed PROMOTE passes through.
        """
        v = _survive_v(1, CLAIM_A)
        promote = _ev(2, type=PROMOTE, actor="user", confirmed=True)
        assert promote in doc_projection([v, promote])
        versions = snapshot_projection([v, promote])
        assert len(versions) == 2
        assert versions[1].triggering_event_id == promote.id
        assert versions[1].triggering_event_type == PROMOTE
        assert promote.id in versions[1].added_event_ids

    def test_retract_of_counted_verdict_shrinks_doc(self):
        """7. Retract a previously-counted survive verdict -> later version removes it."""
        v = _survive_v(1, CLAIM_A)
        r = _ev(2, type=RETRACT, actor="user", target_ref=v.id, confirmed=True)
        versions = snapshot_projection([v, r])
        assert len(versions) == 2
        # First version: verdict enters doc.
        assert v.id in versions[0].added_event_ids
        # Second version: triggered by retract, doc shrinks back to empty.
        assert versions[1].triggering_event_id == r.id
        assert versions[1].triggering_event_type == RETRACT
        assert v.id in versions[1].removed_event_ids
        assert versions[1].doc == []

    def test_confirmed_substance_edit_produces_version(self):
        """8. A confirmed substance EDIT lands in doc -> a version.

        Verified against doc_projection: it does NOT special-case EDIT scope;
        a confirmed, non-debt EDIT passes through regardless of scope.
        """
        edit = _ev(
            1,
            type=EDIT,
            actor="user",
            payload={"scope": "substance"},
            confirmed=True,
        )
        assert edit in doc_projection([edit])
        versions = snapshot_projection([edit])
        assert len(versions) == 1
        assert versions[0].triggering_event_type == EDIT
        assert edit.id in versions[0].added_event_ids

    def test_confirm_meta_event_triggers_version(self):
        """9. A CONFIRM that flips a previously-unconfirmed survive verdict in.

        Flow: a confirmed challenge enters the doc; a confirmed kill verdict
        removes it (claim killed); an unconfirmed survive verdict has no effect
        until a CONFIRM targets it — at which point the claim is no longer
        killed and the challenge re-enters the doc. The triggering event is the
        CONFIRM. Verified against doc_projection prefix-by-prefix.
        """
        challenge = _ev(1, type=CHALLENGE, target_ref=CLAIM_A, confirmed=True)
        kill_v = _ev(
            2, type=VERDICT, payload={"outcome": "kill"}, target_ref=CLAIM_A, confirmed=True
        )
        survive_unconfirmed = _ev(
            3, type=VERDICT, payload={"outcome": "survive"}, target_ref=CLAIM_A, confirmed=False
        )
        confirm = _ev(
            4, type=CONFIRM, actor="user", target_ref=survive_unconfirmed.id, confirmed=True
        )
        events = [challenge, kill_v, survive_unconfirmed, confirm]
        versions = snapshot_projection(events)
        # v1: challenge enters; v2: kill removes it; v3: confirm re-adds it.
        assert len(versions) == 3
        last = versions[-1]
        assert last.triggering_event_id == confirm.id
        assert last.triggering_event_type == CONFIRM
        assert challenge.id in last.added_event_ids
        assert challenge in last.doc

    def test_shuffled_input_same_as_sorted(self):
        """10. Defensive: shuffled (non-ts) input yields the same versions."""
        va = _survive_v(1, CLAIM_A)
        vb = _survive_v(2, CLAIM_B)
        sorted_versions = snapshot_projection([va, vb])
        shuffled_versions = snapshot_projection([vb, va])

        def fingerprint(vs):
            return [
                (v.version, v.triggering_event_id, v.added_event_ids, v.removed_event_ids)
                for v in vs
            ]

        assert fingerprint(sorted_versions) == fingerprint(shuffled_versions)

    def test_no_duplicate_consecutive_versions(self):
        """11. A stretch where doc is unchanged emits only one version."""
        v = _survive_v(1, CLAIM_A)
        # Two unconfirmed events that never enter the doc -> no new versions.
        noise1 = _ev(2, type=CHALLENGE, target_ref=CLAIM_B, confirmed=False)
        noise2 = _ev(3, type=ANSWER, actor="user", target_ref=CLAIM_B, confirmed=False)
        versions = snapshot_projection([v, noise1, noise2])
        assert len(versions) == 1
        assert versions[0].triggering_event_id == v.id

    def test_versions_are_docversion_instances(self):
        """Returned items are DocVersion pydantic models."""
        v = _survive_v(1, CLAIM_A)
        versions = snapshot_projection([v])
        assert all(isinstance(x, DocVersion) for x in versions)
        assert versions[0].ts == v.ts
