"""End-to-end acceptance tests mapping 1:1 to spec section 5.

These tests exercise the 7 acceptance criteria + the debt-blocks-reference
criterion through the SERVICE layer (not HTTP).  Each test walks the full
flow through real services wired to a shared InMemoryEventStore.

Spec reference: docs/spec-trajectory-spine.md section 5
Plan reference: docs/plan-trajectory-spine.md PR #12
"""

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
    Event,
    make_event,
)
from anneal.domain.invariants import DebtBlockError, UngrilledError
from anneal.domain.projections import (
    claim_status,
    doc_projection,
    is_parked,
    lens_feed_projection,
)
from anneal.services.event_service import EventService
from anneal.services.grill_service import GrillService
from anneal.services.lens_feed_service import (
    InMemoryLensFeedStore,
    LensFeedService,
)
from anneal.services.park_service import ParkService
from anneal.services.promote_service import PromoteService
from anneal.store.event_store import InMemoryEventStore


# ---------------------------------------------------------------------------
# Shared fixture: full service stack
# ---------------------------------------------------------------------------

LIBRARY = "lib-acceptance"


class ServiceStack:
    """Container for the full set of wired services."""

    def __init__(self) -> None:
        self.store = InMemoryEventStore()
        self.feed_store = InMemoryLensFeedStore()
        self.event_svc = EventService(self.store)
        self.park_svc = ParkService(self.store, self.event_svc)
        self.grill_svc = GrillService(self.store, self.event_svc)
        self.promote_svc = PromoteService(self.store, self.event_svc)
        self.lens_feed_svc = LensFeedService(
            event_store=self.store, feed_store=self.feed_store
        )


@pytest.fixture
def svc() -> ServiceStack:
    """Create a fresh service stack for each test."""
    return ServiceStack()


# ===========================================================================
# Acceptance criteria
# ===========================================================================


class TestAcceptanceCriteria:
    """End-to-end acceptance tests mapping 1:1 to spec section 5."""

    # -----------------------------------------------------------------------
    # AC1: Park isolation
    # -----------------------------------------------------------------------

    def test_ac1_park_isolation(self, svc: ServiceStack):
        """Section 5.1: Park a灵感, it's in isolation, marked ungrilled,
        not visible in Lens feed queries.

        Steps:
        1. Park an idea via ParkService.
        2. Verify events exist for the artifact (park event present).
        3. Verify is_parked() returns True.
        4. Verify lens_feed_projection returns empty (parked = invisible to Lens).
        5. Verify doc_projection returns empty (parked = not in doc).
        """
        # 1. Park an idea.
        artifact, claim = svc.park_svc.park(LIBRARY, "Ultrasound can detect microcracks")

        # 2. Park event is present in the store.
        events = svc.store.get_events(artifact.id)
        assert len(events) == 1
        assert events[0].type == PARK
        assert events[0].target_ref == claim.id

        # 3. Artifact is in PARK isolation.
        assert is_parked(events) is True

        # 4. Lens feed projection returns nothing for a parked artifact.
        lens_events = lens_feed_projection(events)
        assert lens_events == [], "Parked artifact must be invisible to Lens"

        # 5. Doc projection returns nothing for a parked artifact.
        doc_events = doc_projection(events)
        assert doc_events == [], "Parked artifact must not appear in DOC"

    # -----------------------------------------------------------------------
    # AC2: Park-to-grill cycle
    # -----------------------------------------------------------------------

    def test_ac2_park_to_grill_cycle(self, svc: ServiceStack):
        """Section 5.2: Pull parked item into grill, complete at least one
        challenge -> answer -> verdict round.

        Steps:
        1. Park an idea.
        2. start_grill (validation gate).
        3. challenge (confirmed=False, system-generated).
        4. answer (confirmed=True, user action).
        5. verdict survive (confirmed=False, system judgment).
        6. Confirm the verdict via EventService.
        7. Verify claim_status returns "survived".
        """
        # 1. Park.
        artifact, claim = svc.park_svc.park(LIBRARY, "Phased-array improves resolution")

        # 2. start_grill validates the transition.
        svc.grill_svc.start_grill(artifact.id, artifact.kind)

        # 3. Challenge (system action, unconfirmed).
        challenge_evt = svc.grill_svc.challenge(
            artifact.id, claim.id, "What experimental evidence supports this?"
        )
        assert challenge_evt.type == CHALLENGE
        assert challenge_evt.confirmed is False
        assert challenge_evt.actor == "system"

        # 4. Answer (user action, confirmed).
        answer_evt = svc.grill_svc.answer(
            artifact.id, claim.id, "Study by Zhang et al. 2024 shows 3x improvement"
        )
        assert answer_evt.type == ANSWER
        assert answer_evt.confirmed is True
        assert answer_evt.actor == "user"

        # 5. Verdict survive (system judgment, unconfirmed).
        verdict_evt = svc.grill_svc.verdict(
            artifact.id, claim.id, "survive", "Evidence is solid and reproducible"
        )
        assert verdict_evt.type == VERDICT
        assert verdict_evt.confirmed is False
        assert verdict_evt.payload["outcome"] == "survive"

        # 6. Confirm the system events.
        svc.event_svc.confirm_event(artifact.id, challenge_evt.id)
        svc.event_svc.confirm_event(artifact.id, verdict_evt.id)

        # 7. Verify claim status is "survived".
        events = svc.store.get_events(artifact.id)
        assert claim_status(events, claim.id) == "survived"

    # -----------------------------------------------------------------------
    # AC3: Killed idea persists in trajectory
    # -----------------------------------------------------------------------

    def test_ac3_killed_idea_persists(self, svc: ServiceStack):
        """Section 5.3: During grill, at least one idea is killed.
        It permanently remains in trajectory and is replayable.

        Steps:
        1. Park an idea, start grill.
        2. Challenge, answer, verdict(kill), confirm verdict.
        3. Verify claim_status returns "killed".
        4. Verify the kill verdict event exists in the full event stream.
        5. Verify the kill verdict is NOT in doc_projection (killed = not in doc).
        6. Verify the kill verdict IS in lens_feed_projection (killed = mining material).
        """
        # 1. Park and start grill.
        artifact, claim = svc.park_svc.park(LIBRARY, "Single-element is sufficient")
        svc.grill_svc.start_grill(artifact.id, artifact.kind)

        # 2. Challenge -> answer -> verdict(kill).
        challenge_evt = svc.grill_svc.challenge(
            artifact.id, claim.id, "How do you image without beamforming?"
        )
        svc.grill_svc.answer(
            artifact.id, claim.id, "I assumed plane-wave was enough"
        )
        verdict_evt = svc.grill_svc.verdict(
            artifact.id, claim.id, "kill", "Plane-wave alone insufficient for depth"
        )

        # Confirm system events.
        svc.event_svc.confirm_event(artifact.id, challenge_evt.id)
        svc.event_svc.confirm_event(artifact.id, verdict_evt.id)

        # 3. Claim status is "killed".
        events = svc.store.get_events(artifact.id)
        assert claim_status(events, claim.id) == "killed"

        # 4. Kill verdict is present in the full event stream (permanent, replayable).
        all_verdicts = [
            e for e in events
            if e.type == VERDICT and e.payload.get("outcome") == "kill"
        ]
        assert len(all_verdicts) == 1, "Kill verdict must persist in trajectory"

        # 5. Kill verdict is NOT in doc_projection.
        doc_events = doc_projection(events)
        kill_in_doc = [
            e for e in doc_events
            if e.type == VERDICT and e.payload.get("outcome") == "kill"
        ]
        assert kill_in_doc == [], "Kill verdict must not appear in DOC"

        # 6. Kill verdict IS in lens_feed_projection (killed = mining material).
        lens_events = lens_feed_projection(events)
        kill_in_lens = [
            e for e in lens_events
            if e.type == VERDICT and e.payload.get("outcome") == "kill"
        ]
        assert len(kill_in_lens) == 1, "Kill verdict must appear in Lens feed (mining material)"

    # -----------------------------------------------------------------------
    # AC4: Promote produces a clean DOC
    # -----------------------------------------------------------------------

    def test_ac4_promote_clean_doc(self, svc: ServiceStack):
        """Section 5.4: Survivor promotes to DOC. DOC contains no
        ungrilled / killed content.

        Steps:
        1. Park an idea with TWO claims (simulated via two grill rounds).
        2. Grill both: one survives, one is killed.
        3. Confirm both verdicts.
        4. Promote the survived claim.
        5. get_doc: verify ONLY events related to the survived claim appear.
        6. Verify NO killed verdict, NO park event, NO unconfirmed events in doc.
        """
        # 1. Park an idea.
        artifact, claim_survive = svc.park_svc.park(
            LIBRARY, "Doppler shift detects flow velocity"
        )
        killed_claim_id = "claim-killed-in-grill"

        # 2. Start grill.
        svc.grill_svc.start_grill(artifact.id, artifact.kind)

        # Grill claim_survive -> survive.
        c1 = svc.grill_svc.challenge(
            artifact.id, claim_survive.id, "How accurate is Doppler measurement?"
        )
        svc.grill_svc.answer(
            artifact.id, claim_survive.id, "Within 5% per clinical validation"
        )
        v1 = svc.grill_svc.verdict(
            artifact.id, claim_survive.id, "survive", "Clinically validated"
        )
        svc.event_svc.confirm_event(artifact.id, c1.id)
        svc.event_svc.confirm_event(artifact.id, v1.id)

        # Grill killed_claim_id -> kill.
        c2 = svc.grill_svc.challenge(
            artifact.id, killed_claim_id, "Can you measure absolute pressure?"
        )
        svc.grill_svc.answer(
            artifact.id, killed_claim_id, "Only relative changes"
        )
        v2 = svc.grill_svc.verdict(
            artifact.id, killed_claim_id, "kill", "Cannot measure absolute pressure"
        )
        svc.event_svc.confirm_event(artifact.id, c2.id)
        svc.event_svc.confirm_event(artifact.id, v2.id)

        # 4. Promote the survived claim.
        promote_evt = svc.promote_svc.promote(artifact.id, claim_survive.id)
        assert promote_evt.type == PROMOTE

        # 5-6. get_doc: verify cleanliness.
        doc = svc.promote_svc.get_doc(artifact.id)
        assert len(doc) > 0, "DOC should not be empty after promote"

        for evt in doc:
            # No park events.
            assert evt.type != PARK, "PARK events must not appear in DOC"
            # No debt-bearing events.
            assert evt.debt is False, "Debt-bearing events must not appear in DOC"
            # All must be confirmed.
            assert evt.confirmed is True, "Unconfirmed events must not appear in DOC"
            # No meta-events.
            assert evt.type not in {CONFIRM, RETRACT}, (
                "Meta-events must not appear in DOC"
            )
            # No kill verdicts.
            if evt.type == VERDICT:
                assert evt.payload.get("outcome") != "kill", (
                    "Kill verdicts must not appear in DOC"
                )
            # No events targeting the killed claim.
            assert evt.target_ref != killed_claim_id, (
                f"Events targeting killed claim must not appear in DOC"
            )

        # The survive claim's PROMOTE event should be present.
        promote_events = [e for e in doc if e.type == PROMOTE]
        assert len(promote_events) == 1
        assert promote_events[0].target_ref == claim_survive.id

    # -----------------------------------------------------------------------
    # AC5: Lens feed write
    # -----------------------------------------------------------------------

    def test_ac5_lens_feed_write(self, svc: ServiceStack):
        """Section 5.5: Complete trajectory can be written to Lens feed point
        (even if downstream just persists, no learning).

        Steps:
        1. Park, grill (survive + kill on separate artifacts), confirm all verdicts.
        2. Ingest trajectory into Lens feed.
        3. query_feed returns entries.
        4. Both survived AND killed events appear (killed = mining material).
        5. Park event does NOT appear in feed.
        """
        # 1a. Park and grill -> survive.
        art_s, claim_s = svc.park_svc.park(LIBRARY, "Hypothesis that survives")
        svc.grill_svc.start_grill(art_s.id, art_s.kind)
        c_s = svc.grill_svc.challenge(art_s.id, claim_s.id, "Evidence?")
        svc.grill_svc.answer(art_s.id, claim_s.id, "Paper A confirms this")
        v_s = svc.grill_svc.verdict(art_s.id, claim_s.id, "survive", "Solid")
        svc.event_svc.confirm_event(art_s.id, c_s.id)
        svc.event_svc.confirm_event(art_s.id, v_s.id)

        # 1b. Park and grill -> kill (separate artifact).
        art_k, claim_k = svc.park_svc.park(LIBRARY, "Hypothesis that dies")
        svc.grill_svc.start_grill(art_k.id, art_k.kind)
        c_k = svc.grill_svc.challenge(art_k.id, claim_k.id, "Any support?")
        svc.grill_svc.answer(art_k.id, claim_k.id, "None found")
        v_k = svc.grill_svc.verdict(art_k.id, claim_k.id, "kill", "No evidence")
        svc.event_svc.confirm_event(art_k.id, c_k.id)
        svc.event_svc.confirm_event(art_k.id, v_k.id)

        # 2. Ingest both trajectories into Lens feed.
        entries_s = svc.lens_feed_svc.ingest(art_s.id, LIBRARY)
        entries_k = svc.lens_feed_svc.ingest(art_k.id, LIBRARY)

        assert len(entries_s) > 0, "Survived trajectory should produce feed entries"
        assert len(entries_k) > 0, "Killed trajectory should produce feed entries"

        # 3. query_feed returns all entries.
        all_entries = svc.lens_feed_svc.query_feed(LIBRARY)
        assert len(all_entries) == len(entries_s) + len(entries_k)

        # 4. Both survive and kill verdicts appear in the feed.
        entry_types = {e.event_type for e in all_entries}
        assert VERDICT in entry_types, "Verdict events must appear in Lens feed"
        assert CHALLENGE in entry_types, "Challenge events must appear in Lens feed"
        assert ANSWER in entry_types, "Answer events must appear in Lens feed"

        # Specifically verify kill verdict is in the feed.
        kill_entries = [
            e for e in entries_k if e.event_type == VERDICT
        ]
        assert len(kill_entries) >= 1, "Kill verdict must be in Lens feed (mining material)"

        # 5. Park event does NOT appear in the feed.
        park_entries = [e for e in all_entries if e.event_type == PARK]
        assert park_entries == [], "Park events must not appear in Lens feed"

    # -----------------------------------------------------------------------
    # AC6: Unified schema (idea + review use same verbs)
    # -----------------------------------------------------------------------

    def test_ac6_unified_schema(self, svc: ServiceStack):
        """Section 5.6: Both idea and review flows use the same trajectory
        schema (proof of unified verbs).

        Steps:
        1. Run the IDENTICAL flow twice: once with kind="idea", once with kind="review".
        2. Both produce the same event types (PARK, CHALLENGE, ANSWER, VERDICT).
        3. Both use the same projections (doc_projection, lens_feed_projection).
        4. Assert structural equivalence of event type sequences.
        """
        def run_flow(kind: str) -> list[str]:
            """Run a full park->grill->survive->promote flow and return event type sequence."""
            artifact, claim = svc.park_svc.park(LIBRARY, f"Hypothesis ({kind})", kind=kind)

            svc.grill_svc.start_grill(artifact.id, artifact.kind)

            challenge = svc.grill_svc.challenge(
                artifact.id, claim.id, "What is the evidence?"
            )
            svc.grill_svc.answer(
                artifact.id, claim.id, "Evidence from study Z"
            )
            verdict = svc.grill_svc.verdict(
                artifact.id, claim.id, "survive", "Evidence holds"
            )

            svc.event_svc.confirm_event(artifact.id, challenge.id)
            svc.event_svc.confirm_event(artifact.id, verdict.id)

            svc.promote_svc.promote(artifact.id, claim.id)

            events = svc.store.get_events(artifact.id)

            # Extract the sequence of core event types (exclude CONFIRM meta-events).
            core_types = [
                e.type for e in events if e.type not in {CONFIRM, RETRACT}
            ]

            # Also verify projections work identically.
            doc = doc_projection(events)
            lens = lens_feed_projection(events)
            assert len(doc) > 0, f"doc_projection must work for kind={kind}"
            assert len(lens) > 0, f"lens_feed_projection must work for kind={kind}"

            return core_types

        # 1. Run identical flow for both kinds.
        idea_types = run_flow("idea")
        review_types = run_flow("review")

        # 2-4. Both produce the exact same sequence of event types.
        assert idea_types == review_types, (
            f"Idea and review must use the same event type sequence.\n"
            f"  idea:   {idea_types}\n"
            f"  review: {review_types}"
        )

        # Verify the expected types are present.
        assert PARK in idea_types
        assert CHALLENGE in idea_types
        assert ANSWER in idea_types
        assert VERDICT in idea_types
        assert PROMOTE in idea_types

    # -----------------------------------------------------------------------
    # AC7: Debt blocks promote
    # -----------------------------------------------------------------------

    def test_ac7_debt_blocks_promote(self, svc: ServiceStack):
        """Section 5.7: Attempting to promote a debt=True claim is
        hard-blocked. Clearing debt allows promotion.

        Steps:
        1. Park, grill with a full survive cycle (confirmed, no debt).
        2. Add a SEPARATE debt-bearing event (e.g., draft with debt=True).
        3. Try promote -> DebtBlockError (draft has unresolved debt).
        4. Confirm the draft via EventService.
        5. Try promote again -> succeeds.
        """
        # 1. Park and grill -> survive (clean, confirmed, no debt).
        artifact, claim = svc.park_svc.park(LIBRARY, "Claim to test debt gate")
        svc.grill_svc.start_grill(artifact.id, artifact.kind)

        challenge = svc.grill_svc.challenge(artifact.id, claim.id, "Evidence?")
        svc.grill_svc.answer(artifact.id, claim.id, "Paper B shows X")
        verdict = svc.grill_svc.verdict(
            artifact.id, claim.id, "survive", "Convincing"
        )
        svc.event_svc.confirm_event(artifact.id, challenge.id)
        svc.event_svc.confirm_event(artifact.id, verdict.id)

        # 2. Inject a debt-bearing DRAFT event targeting this claim.
        debt_draft = make_event(
            type=DRAFT,
            actor="system",
            confirmed=False,
            debt=True,
            target_ref=claim.id,
            payload={"content": "Auto-generated draft text"},
        )
        svc.store.append(artifact.id, debt_draft)

        # 3. Promote should fail -- unresolved debt.
        with pytest.raises(DebtBlockError, match="unresolved debt"):
            svc.promote_svc.promote(artifact.id, claim.id)

        # 4. Confirm the debt-bearing draft event (clear the debt).
        svc.event_svc.confirm_event(artifact.id, debt_draft.id)

        # 5. Promote now succeeds.
        evt = svc.promote_svc.promote(artifact.id, claim.id)
        assert evt.type == PROMOTE
        assert evt.target_ref == claim.id

    # -----------------------------------------------------------------------
    # AC8: Debt blocks reference (spec section 4 Q-D, third trigger)
    # -----------------------------------------------------------------------

    def test_ac8_debt_blocks_reference(self, svc: ServiceStack):
        """Section 4 Q-D: Referencing a claim with unresolved debt is
        hard-blocked.

        Steps:
        1. Park, grill, bypass without confirming.
        2. reference_claim -> DebtBlockError.
        3. Confirm the bypass.
        4. reference_claim -> succeeds.
        """
        # 1. Park and grill with bypass (debt=True, confirmed=False).
        artifact, claim = svc.park_svc.park(LIBRARY, "Bypassed claim")
        svc.grill_svc.start_grill(artifact.id, artifact.kind)

        # Need at least one challenge before bypass.
        challenge = svc.grill_svc.challenge(artifact.id, claim.id, "Evidence?")
        svc.event_svc.confirm_event(artifact.id, challenge.id)

        bypass_evt = svc.grill_svc.bypass(artifact.id, claim.id)
        assert bypass_evt.debt is True
        assert bypass_evt.confirmed is False

        # 2. Reference should fail -- unresolved debt.
        with pytest.raises(DebtBlockError, match="unresolved debt"):
            svc.promote_svc.reference_claim(artifact.id, claim.id)

        # 3. Confirm the bypass verdict (clears the debt).
        svc.event_svc.confirm_event(artifact.id, bypass_evt.id)

        # 4. Reference now succeeds (no exception raised).
        svc.promote_svc.reference_claim(artifact.id, claim.id)
