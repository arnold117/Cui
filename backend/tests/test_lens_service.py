"""Tests for anneal.services.lens_service — cross-idea contradiction (L3 tracer).

Past claims are grilled the realistic way (challenge + verdict, then confirm via
EventService) so ``claim_status`` actually returns survived/killed. The LLM is
faked; no network, no real model.
"""

from __future__ import annotations

import json

import pytest

from anneal.domain.events import CHALLENGE, PARK, make_event
from anneal.domain.models import Artifact, Claim
from anneal.llm.errors import LLMNotConfiguredError
from anneal.services.event_service import EventService
from anneal.services.lens_service import LensService
from anneal.store.event_store import InMemoryEventStore
from anneal.store.repository import InMemoryRepository
from tests.fakes import FakeLLMClient


LIB = "lib-1"
CUR_ARTIFACT = "art-current"
CUR_CLAIM = "claim-current"


# ---------------------------------------------------------------------------
# Fixtures + helpers
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


def _make_svc(store, event_svc, repo, responses):
    llm = FakeLLMClient([json.dumps(r) for r in responses]) if responses is not None else None
    return LensService(store, event_svc, repo=repo, llm=llm)


def _register_current(repo):
    """Register the current artifact + claim (parked, mid-grill)."""
    repo.create_artifact(Artifact(id=CUR_ARTIFACT, library_id=LIB, kind="idea", goal="g"))
    repo.create_claim(
        Claim(id=CUR_CLAIM, library_id=LIB, body="X causes Y", artifact_ids=[CUR_ARTIFACT])
    )


def _seed_grilled_claim(
    store,
    event_svc,
    repo,
    *,
    claim_id: str,
    artifact_id: str,
    body: str,
    outcome: str,
    library_id: str = LIB,
) -> Claim:
    """Seed a fully-grilled claim whose claim_status is survived/killed.

    Park -> challenge -> verdict, then CONFIRM the verdict via EventService so
    claim_status counts it.
    """
    repo.create_artifact(Artifact(id=artifact_id, library_id=library_id, kind="idea", goal="g"))
    claim = Claim(id=claim_id, library_id=library_id, body=body, artifact_ids=[artifact_id])
    repo.create_claim(claim)

    store.append(
        artifact_id,
        make_event(type=PARK, actor="user", confirmed=True, target_ref=claim_id, payload={"kind": "idea"}),
    )
    store.append(
        artifact_id,
        make_event(type=CHALLENGE, actor="system", confirmed=True, target_ref=claim_id, payload={"question": "q"}),
    )
    from anneal.domain.events import VERDICT
    verdict = make_event(
        type=VERDICT, actor="system", confirmed=False, target_ref=claim_id,
        payload={"outcome": "survive" if outcome == "survived" else "kill", "rationale": "r"},
    )
    event_svc.append_event(artifact_id, verdict)
    event_svc.confirm_event(artifact_id, verdict.id)
    return claim


def _seed_parked_only_claim(store, repo, *, claim_id, artifact_id, body):
    """Seed a claim that is only PARKED (never grilled) → status 'parked'."""
    repo.create_artifact(Artifact(id=artifact_id, library_id=LIB, kind="idea", goal="g"))
    repo.create_claim(Claim(id=claim_id, library_id=LIB, body=body, artifact_ids=[artifact_id]))
    store.append(
        artifact_id,
        make_event(type=PARK, actor="user", confirmed=True, target_ref=claim_id, payload={"kind": "idea"}),
    )


HIT = {"contradicts": True, "tension_type": "hard", "tension": "X vs not-X", "question": "How reconcile?"}
SOFT = {"contradicts": True, "tension_type": "soft", "tension": "same method", "question": "Yet another variant?"}
MISS = {"contradicts": False, "tension_type": "hard", "tension": "", "question": ""}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScanContradictions:
    def test_survived_past_claim_surfaces_pending_challenge(self, store, event_svc, repo):
        _register_current(repo)
        _seed_grilled_claim(
            store, event_svc, repo, claim_id="past-s", artifact_id="art-past",
            body="X causes Y is false", outcome="survived",
        )
        svc = _make_svc(store, event_svc, repo, [HIT])

        events = svc.scan_contradictions(CUR_ARTIFACT, CUR_CLAIM, "X causes Y")

        assert len(events) == 1
        ev = events[0]
        assert ev.type == CHALLENGE
        assert ev.actor == "system"
        assert ev.confirmed is False
        assert ev.target_ref == CUR_CLAIM
        p = ev.payload
        assert p["kind"] == "lens_contradiction"
        assert p["past_claim_id"] == "past-s"
        assert p["past_artifact_id"] == "art-past"
        assert p["past_outcome"] == "survived"
        assert p["tension_type"] == "hard"
        assert p["question"] == "How reconcile?"
        assert p["auto_generated"] is True
        # event was actually appended to the current artifact's stream
        assert any(e.id == ev.id for e in store.get_events(CUR_ARTIFACT))

    def test_killed_past_claim_surfaces(self, store, event_svc, repo):
        _register_current(repo)
        _seed_grilled_claim(
            store, event_svc, repo, claim_id="past-k", artifact_id="art-past",
            body="X causes Y was tried and fails", outcome="killed",
        )
        svc = _make_svc(store, event_svc, repo, [HIT])

        events = svc.scan_contradictions(CUR_ARTIFACT, CUR_CLAIM, "X causes Y")

        assert len(events) == 1
        assert events[0].payload["past_outcome"] == "killed"

    def test_parked_only_claim_not_candidate(self, store, event_svc, repo):
        _register_current(repo)
        _seed_parked_only_claim(
            store, repo, claim_id="past-p", artifact_id="art-past",
            body="X causes Y maybe",
        )
        svc = _make_svc(store, event_svc, repo, [HIT])

        events = svc.scan_contradictions(CUR_ARTIFACT, CUR_CLAIM, "X causes Y")
        assert events == []

    def test_different_library_excluded(self, store, event_svc, repo):
        _register_current(repo)
        _seed_grilled_claim(
            store, event_svc, repo, claim_id="past-other", artifact_id="art-other",
            body="X causes Y refuted", outcome="survived", library_id="lib-OTHER",
        )
        svc = _make_svc(store, event_svc, repo, [HIT])

        events = svc.scan_contradictions(CUR_ARTIFACT, CUR_CLAIM, "X causes Y")
        assert events == []

    def test_current_claim_excluded(self, store, event_svc, repo):
        """A grilled claim that IS the current claim is not a candidate."""
        _register_current(repo)
        # Grill the current claim itself in its own artifact.
        store.append(
            CUR_ARTIFACT,
            make_event(type=PARK, actor="user", confirmed=True, target_ref=CUR_CLAIM, payload={"kind": "idea"}),
        )
        from anneal.domain.events import VERDICT
        v = make_event(type=VERDICT, actor="system", confirmed=False, target_ref=CUR_CLAIM,
                       payload={"outcome": "survive", "rationale": "r"})
        event_svc.append_event(CUR_ARTIFACT, v)
        event_svc.confirm_event(CUR_ARTIFACT, v.id)
        svc = _make_svc(store, event_svc, repo, [HIT])

        events = svc.scan_contradictions(CUR_ARTIFACT, CUR_CLAIM, "X causes Y")
        assert events == []

    def test_same_artifact_claim_excluded(self, store, event_svc, repo):
        """A grilled claim sharing the current artifact is excluded."""
        _register_current(repo)
        # Another claim parked on the SAME current artifact, grilled survived.
        sibling = Claim(id="sibling", library_id=LIB, body="X causes Y too", artifact_ids=[CUR_ARTIFACT])
        repo.create_claim(sibling)
        store.append(
            CUR_ARTIFACT,
            make_event(type=PARK, actor="user", confirmed=True, target_ref="sibling", payload={"kind": "idea"}),
        )
        from anneal.domain.events import VERDICT
        v = make_event(type=VERDICT, actor="system", confirmed=False, target_ref="sibling",
                       payload={"outcome": "survive", "rationale": "r"})
        event_svc.append_event(CUR_ARTIFACT, v)
        event_svc.confirm_event(CUR_ARTIFACT, v.id)
        svc = _make_svc(store, event_svc, repo, [HIT])

        events = svc.scan_contradictions(CUR_ARTIFACT, CUR_CLAIM, "X causes Y")
        assert events == []

    def test_soft_dropped_by_default(self, store, event_svc, repo):
        _register_current(repo)
        _seed_grilled_claim(
            store, event_svc, repo, claim_id="past-soft", artifact_id="art-past",
            body="X causes Y variant", outcome="survived",
        )
        svc = _make_svc(store, event_svc, repo, [SOFT])

        events = svc.scan_contradictions(CUR_ARTIFACT, CUR_CLAIM, "X causes Y", include_soft=False)
        assert events == []

    def test_soft_surfaced_when_included(self, store, event_svc, repo):
        _register_current(repo)
        _seed_grilled_claim(
            store, event_svc, repo, claim_id="past-soft", artifact_id="art-past",
            body="X causes Y variant", outcome="survived",
        )
        svc = _make_svc(store, event_svc, repo, [SOFT])

        events = svc.scan_contradictions(CUR_ARTIFACT, CUR_CLAIM, "X causes Y", include_soft=True)
        assert len(events) == 1
        assert events[0].payload["tension_type"] == "soft"

    def test_no_contradiction_no_event(self, store, event_svc, repo):
        _register_current(repo)
        _seed_grilled_claim(
            store, event_svc, repo, claim_id="past-miss", artifact_id="art-past",
            body="X causes Y unrelated topic", outcome="survived",
        )
        svc = _make_svc(store, event_svc, repo, [MISS])

        events = svc.scan_contradictions(CUR_ARTIFACT, CUR_CLAIM, "X causes Y")
        assert events == []

    def test_llm_none_raises(self, store, event_svc, repo):
        _register_current(repo)
        svc = _make_svc(store, event_svc, repo, None)
        with pytest.raises(LLMNotConfiguredError):
            svc.scan_contradictions(CUR_ARTIFACT, CUR_CLAIM, "X causes Y")

    def test_missing_artifact_raises(self, store, event_svc, repo):
        svc = _make_svc(store, event_svc, repo, [HIT])
        with pytest.raises(ValueError, match="not found"):
            svc.scan_contradictions("no-such-artifact", CUR_CLAIM, "X causes Y")

    def test_no_taste_or_score_key_in_payload(self, store, event_svc, repo):
        """Red line: no quality/score/rating key ever appears in a produced payload."""
        _register_current(repo)
        _seed_grilled_claim(
            store, event_svc, repo, claim_id="past-s", artifact_id="art-past",
            body="X causes Y is false", outcome="survived",
        )
        svc = _make_svc(store, event_svc, repo, [HIT])

        events = svc.scan_contradictions(CUR_ARTIFACT, CUR_CLAIM, "X causes Y")
        banned = {"score", "quality", "rating", "taste", "merit", "rank", "novelty"}
        for ev in events:
            assert banned.isdisjoint(ev.payload.keys())
