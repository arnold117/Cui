"""Tests for LensService.assess_taste + build_taste_prompt (Lens 第二刀 / 品味锚).

Past claims are grilled the realistic way (park -> challenge -> verdict -> confirm
via EventService) so ``claim_status`` actually returns survived/killed. The LLM is
faked and ``search_openalex`` is monkeypatched — no network, no real model.
"""

from __future__ import annotations

import json

import pytest

from anneal.domain.events import CHALLENGE, PARK, VERDICT, make_event
from anneal.domain.models import Artifact, Claim
from anneal.llm.errors import LLMNotConfiguredError
from anneal.llm.prompts import build_taste_prompt
from anneal.services import lens_service as lens_module
from anneal.services.event_service import EventService
from anneal.services.lens_service import LensService
from anneal.store.event_store import InMemoryEventStore
from anneal.store.repository import InMemoryRepository
from tests.fakes import FakeLLMClient


LIB = "lib-1"
CUR_ARTIFACT = "art-current"
CUR_CLAIM = "claim-current"
CUR_BODY = "Transformer attention improves protein folding prediction"


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


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Default: literature search returns []. Tests override via _set_papers."""
    async def _empty(query, max_results=5, mailto=None):
        return []

    monkeypatch.setattr(lens_module, "search_openalex", _empty)


def _set_papers(monkeypatch, papers):
    async def _fake(query, max_results=5, mailto=None):
        return papers

    monkeypatch.setattr(lens_module, "search_openalex", _fake)


def _make_svc(store, event_svc, repo, responses):
    llm = FakeLLMClient([json.dumps(r) for r in responses]) if responses is not None else None
    return LensService(store, event_svc, repo=repo, llm=llm)


def _register_current(repo):
    repo.create_artifact(Artifact(id=CUR_ARTIFACT, library_id=LIB, kind="idea", goal="g"))
    repo.create_claim(
        Claim(id=CUR_CLAIM, library_id=LIB, body=CUR_BODY, artifact_ids=[CUR_ARTIFACT])
    )


def _seed_grilled_claim(
    store, event_svc, repo, *, claim_id, artifact_id, body, outcome, library_id=LIB
) -> Claim:
    """Seed a fully-grilled claim whose claim_status is survived/killed."""
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
    verdict = make_event(
        type=VERDICT, actor="system", confirmed=False, target_ref=claim_id,
        payload={"outcome": "survive" if outcome == "survived" else "kill", "rationale": "r"},
    )
    event_svc.append_event(artifact_id, verdict)
    event_svc.confirm_event(artifact_id, verdict.id)
    return claim


# A past claim sharing topic terms with CUR_BODY so the prefilter keeps it.
PAST_BODY = "Transformer attention models for protein structure"
PAPER = {"title": "Attention is all you fold", "abstract": "we apply attention to folding", "source_id": "W1"}


def _tier(tier, *, papers=None, claims=None, reasoning="relative positioning", question="increment?"):
    return {
        "tier": tier,
        "reasoning": reasoning,
        "anchored_papers": papers or [],
        "anchored_claims": claims or [],
        "question": question,
    }


# ---------------------------------------------------------------------------
# assess_taste
# ---------------------------------------------------------------------------


class TestAssessTaste:
    async def test_anchored_to_past_claim_surfaces_pending_challenge(
        self, store, event_svc, repo
    ):
        _register_current(repo)
        _seed_grilled_claim(
            store, event_svc, repo, claim_id="past-s", artifact_id="art-past",
            body=PAST_BODY, outcome="survived",
        )
        result = _tier("incremental", claims=[{"past_claim_id": "past-s"}])
        svc = _make_svc(store, event_svc, repo, [result])

        events = await svc.assess_taste(CUR_ARTIFACT, CUR_CLAIM, CUR_BODY)

        assert len(events) == 1
        ev = events[0]
        assert ev.type == CHALLENGE
        assert ev.actor == "system"
        assert ev.confirmed is False
        assert ev.target_ref == CUR_CLAIM
        p = ev.payload
        assert p["kind"] == "taste"
        assert p["tier"] == "incremental"
        assert p["anchored_claims"] == [{"past_claim_id": "past-s"}]
        assert p["auto_generated"] is True
        # actually appended to the current stream
        assert any(e.id == ev.id for e in store.get_events(CUR_ARTIFACT))

    async def test_cold_start_no_history_returns_empty_even_with_papers(
        self, store, event_svc, repo, monkeypatch
    ):
        """Q-G gate: no grilled history → silent, even if literature has hits."""
        _register_current(repo)
        _set_papers(monkeypatch, [PAPER])
        # LLM would anchor to the paper, but the history gate fires first.
        result = _tier("novel_but_tasteless", papers=[{"title": PAPER["title"]}])
        svc = _make_svc(store, event_svc, repo, [result])

        events = await svc.assess_taste(CUR_ARTIFACT, CUR_CLAIM, CUR_BODY)
        assert events == []

    async def test_hallucinated_anchors_dropped_returns_empty(
        self, store, event_svc, repo, monkeypatch
    ):
        """No-anchor enforcement: anchors matching no real paper/claim → no verdict."""
        _register_current(repo)
        _seed_grilled_claim(
            store, event_svc, repo, claim_id="past-s", artifact_id="art-past",
            body=PAST_BODY, outcome="survived",
        )
        _set_papers(monkeypatch, [PAPER])
        result = _tier(
            "tasteful",
            papers=[{"title": "A paper that was never returned"}],
            claims=[{"past_claim_id": "claim-that-does-not-exist"}],
        )
        svc = _make_svc(store, event_svc, repo, [result])

        events = await svc.assess_taste(CUR_ARTIFACT, CUR_CLAIM, CUR_BODY)
        assert events == []

    async def test_degraded_no_literature_still_surfaces_on_history(
        self, store, event_svc, repo
    ):
        """History present, literature search returns [] → still surfaces."""
        _register_current(repo)
        _seed_grilled_claim(
            store, event_svc, repo, claim_id="past-k", artifact_id="art-past",
            body=PAST_BODY, outcome="killed",
        )
        # no_network fixture leaves search_openalex returning []
        result = _tier("replication", claims=[{"past_claim_id": "past-k"}])
        svc = _make_svc(store, event_svc, repo, [result])

        events = await svc.assess_taste(CUR_ARTIFACT, CUR_CLAIM, CUR_BODY)
        assert len(events) == 1
        assert events[0].payload["tier"] == "replication"
        assert events[0].payload["anchored_claims"] == [{"past_claim_id": "past-k"}]
        assert events[0].payload["anchored_papers"] == []

    async def test_paper_anchor_kept_when_matches_returned_paper(
        self, store, event_svc, repo, monkeypatch
    ):
        _register_current(repo)
        _seed_grilled_claim(
            store, event_svc, repo, claim_id="past-s", artifact_id="art-past",
            body=PAST_BODY, outcome="survived",
        )
        _set_papers(monkeypatch, [PAPER])
        result = _tier(
            "incremental",
            papers=[{"title": PAPER["title"]}, {"title": "fabricated"}],
            claims=[{"past_claim_id": "past-s"}, {"past_claim_id": "ghost"}],
        )
        svc = _make_svc(store, event_svc, repo, [result])

        events = await svc.assess_taste(CUR_ARTIFACT, CUR_CLAIM, CUR_BODY)
        assert len(events) == 1
        p = events[0].payload
        # only the real anchors survive filtering
        assert p["anchored_papers"] == [{"title": PAPER["title"]}]
        assert p["anchored_claims"] == [{"past_claim_id": "past-s"}]

    async def test_invalid_tier_returns_empty(self, store, event_svc, repo):
        _register_current(repo)
        _seed_grilled_claim(
            store, event_svc, repo, claim_id="past-s", artifact_id="art-past",
            body=PAST_BODY, outcome="survived",
        )
        result = _tier("amazing", claims=[{"past_claim_id": "past-s"}])
        svc = _make_svc(store, event_svc, repo, [result])

        events = await svc.assess_taste(CUR_ARTIFACT, CUR_CLAIM, CUR_BODY)
        assert events == []

    async def test_llm_none_raises(self, store, event_svc, repo):
        _register_current(repo)
        svc = _make_svc(store, event_svc, repo, None)
        with pytest.raises(LLMNotConfiguredError):
            await svc.assess_taste(CUR_ARTIFACT, CUR_CLAIM, CUR_BODY)

    async def test_missing_artifact_raises(self, store, event_svc, repo):
        svc = _make_svc(store, event_svc, repo, [_tier("incremental")])
        with pytest.raises(ValueError, match="not found"):
            await svc.assess_taste("no-such-artifact", CUR_CLAIM, CUR_BODY)

    async def test_no_score_key_in_payload(self, store, event_svc, repo):
        """Red line: no numeric/absolute score key ever appears."""
        _register_current(repo)
        _seed_grilled_claim(
            store, event_svc, repo, claim_id="past-s", artifact_id="art-past",
            body=PAST_BODY, outcome="survived",
        )
        result = _tier("incremental", claims=[{"past_claim_id": "past-s"}])
        svc = _make_svc(store, event_svc, repo, [result])

        events = await svc.assess_taste(CUR_ARTIFACT, CUR_CLAIM, CUR_BODY)
        banned = {"score", "quality", "rating", "merit", "rank", "confidence"}
        for ev in events:
            assert banned.isdisjoint(ev.payload.keys())


# ---------------------------------------------------------------------------
# build_taste_prompt
# ---------------------------------------------------------------------------


class TestBuildTastePrompt:
    def _past(self):
        return [("old claim body", "killed", "past-1")]

    def test_includes_both_axes_framing(self):
        system, user = build_taste_prompt(
            "current", [PAPER], self._past()
        )
        low = system.lower()
        assert "novelty" in low
        assert "taste" in low or "worth" in low
        # red line: taste never derived from consensus
        assert "consensus" in low

    def test_includes_anti_praise_instruction(self):
        system, _ = build_taste_prompt("current", [PAPER], self._past())
        low = system.lower()
        assert "praise" in low
        assert "failure mode" in low

    def test_demands_json(self):
        system, _ = build_taste_prompt("current", [PAPER], self._past())
        assert "JSON" in system
        assert '"tier"' in system

    def test_forbids_absolute_scoring(self):
        system, _ = build_taste_prompt("current", [PAPER], self._past())
        low = system.lower()
        assert "score" in low  # appears in a NEVER-score instruction
        assert "never score" in low or "do not output any absolute" in low

    def test_handles_empty_prior_art(self):
        system, user = build_taste_prompt("current", [], self._past())
        # degraded: prompt still well-formed, notes literature did not match
        assert "none" in user.lower()
        assert "past-1" in user  # history anchor still carried

    def test_user_carries_claim_papers_and_history(self):
        system, user = build_taste_prompt(
            "my current claim", [PAPER], [("old body here", "survived", "px")]
        )
        assert "my current claim" in user
        assert PAPER["title"] in user
        assert "old body here" in user
        assert "px" in user
        assert "survived" in user
