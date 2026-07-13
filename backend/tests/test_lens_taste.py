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
from anneal.llm.prompts import ClaimPrecedent, build_taste_prompt
from anneal.services import lens_service as lens_module
from anneal.services.event_service import EventService
from anneal.services.lens_service import LensService
from anneal.store.event_store import InMemoryEventStore
from anneal.store.repository import InMemoryRepository
from tests.fakes import CapturingLLMClient, FakeLLMClient


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
    store, event_svc, repo, *, claim_id, artifact_id, body, outcome, library_id=LIB,
    rationale="r", death_cause=None, revival_condition=None,
) -> Claim:
    """Seed a fully-grilled claim whose claim_status is survived/killed.

    Optional 死因分诊 fields land in the verdict payload; the None default
    seeds a legacy-shaped verdict (recorded before triage).
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
    payload = {"outcome": "survive" if outcome == "survived" else "kill", "rationale": rationale}
    if death_cause is not None:
        payload["death_cause"] = death_cause
    if revival_condition is not None:
        payload["revival_condition"] = revival_condition
    verdict = make_event(
        type=VERDICT, actor="system", confirmed=False, target_ref=claim_id,
        payload=payload,
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
        return [ClaimPrecedent(body="old claim body", outcome="killed", claim_id="past-1")]

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
            "my current claim",
            [PAPER],
            [ClaimPrecedent(body="old body here", outcome="survived", claim_id="px")],
        )
        assert "my current claim" in user
        assert PAPER["title"] in user
        assert "old body here" in user
        assert "px" in user
        assert "survived" in user


# ---------------------------------------------------------------------------
# 判例注入 (spec-verdict-precedent §2 Q4) — the taste anchor eats the quadruple
# ---------------------------------------------------------------------------


class TestTastePromptPrecedent:
    def test_not_worth_precedent_rendered_per_claim(self):
        past = [ClaimPrecedent(
            body="old body", outcome="killed", claim_id="past-1",
            death_cause="not_worth", rationale="right but a dead end",
        )]
        _system, user = build_taste_prompt("current", [], past)
        assert "not_worth" in user
        assert "right but a dead end" in user

    def test_rationale_truncated_at_300(self):
        past = [ClaimPrecedent(
            body="old body", outcome="killed", claim_id="past-1",
            death_cause="refuted", rationale="R" * 400,
        )]
        _system, user = build_taste_prompt("current", [], past)
        assert "R" * 300 + "…" in user
        assert "R" * 301 not in user

    def test_revival_condition_only_for_circumstantial(self):
        past = [
            ClaimPrecedent(
                body="c1", outcome="killed", claim_id="p1",
                death_cause="circumstantial", rationale="shelved",
                revival_condition="dataset D goes public",
            ),
            ClaimPrecedent(
                body="c2", outcome="killed", claim_id="p2",
                death_cause="refuted", rationale="wrong",
                revival_condition="must never render",
            ),
        ]
        _system, user = build_taste_prompt("current", [], past)
        assert "dataset D goes public" in user
        assert "must never render" not in user

    def test_legacy_kill_marked_unclassified(self):
        past = [ClaimPrecedent(body="old", outcome="killed", claim_id="p1")]
        _system, user = build_taste_prompt("current", [], past)
        assert "unclassified" in user

    def test_survived_claim_no_death_cause_line(self):
        past = [ClaimPrecedent(
            body="old", outcome="survived", claim_id="p1", rationale="held up",
        )]
        _system, user = build_taste_prompt("current", [], past)
        assert "held up" in user
        assert "Death cause" not in user

    def test_system_marks_not_worth_as_strongest_signal(self):
        """① 灵魂: not_worth 判例 = revealed taste 最高信号，显式标出."""
        system, _user = build_taste_prompt(
            "current", [], [ClaimPrecedent(body="b", outcome="killed", claim_id="p")]
        )
        low = system.lower()
        assert "not_worth" in system
        assert "strongest revealed-taste signal" in low

    def test_four_anti_sycophancy_layers_intact(self):
        """The death-cause paragraph must not displace the four layers."""
        system, _user = build_taste_prompt(
            "current", [PAPER],
            [ClaimPrecedent(body="b", outcome="killed", claim_id="p",
                            death_cause="not_worth", rationale="r")],
        )
        assert "NO ANCHOR, NO VERDICT" in system
        assert "ANCHOR FIRST" in system
        assert "SKEPTICAL, ASYMMETRIC BAR" in system
        assert "NEVER SCORE" in system


class TestAssessTastePrecedentInjection:
    async def test_quadruple_reaches_llm_prompt(self, store, event_svc, repo):
        """Service-level: the seeded verdict's triage fields land in the prompt."""
        _register_current(repo)
        _seed_grilled_claim(
            store, event_svc, repo, claim_id="past-nw", artifact_id="art-past",
            body=PAST_BODY, outcome="killed",
            rationale="correct but not worth the effort " + "x" * 400,
            death_cause="not_worth",
        )
        result = _tier("novel_but_tasteless", claims=[{"past_claim_id": "past-nw"}])
        llm = CapturingLLMClient([json.dumps(result)])
        svc = LensService(store, event_svc, repo=repo, llm=llm)

        events = await svc.assess_taste(CUR_ARTIFACT, CUR_CLAIM, CUR_BODY)

        assert len(events) == 1
        assert "not_worth" in llm.last_user
        assert "correct but not worth the effort" in llm.last_user
        # deterministic 300-char cap + ellipsis
        assert "…" in llm.last_user
        assert "x" * 300 not in llm.last_user.replace("x" * 300 + "…", "")

    async def test_legacy_claim_injected_as_unclassified(
        self, store, event_svc, repo
    ):
        _register_current(repo)
        _seed_grilled_claim(
            store, event_svc, repo, claim_id="past-legacy", artifact_id="art-past",
            body=PAST_BODY, outcome="killed",
        )
        result = _tier("incremental", claims=[{"past_claim_id": "past-legacy"}])
        llm = CapturingLLMClient([json.dumps(result)])
        svc = LensService(store, event_svc, repo=repo, llm=llm)

        await svc.assess_taste(CUR_ARTIFACT, CUR_CLAIM, CUR_BODY)

        assert "unclassified" in llm.last_user

    async def test_circumstantial_revival_reaches_prompt(
        self, store, event_svc, repo
    ):
        _register_current(repo)
        _seed_grilled_claim(
            store, event_svc, repo, claim_id="past-c", artifact_id="art-past",
            body=PAST_BODY, outcome="killed",
            rationale="cannot defend today",
            death_cause="circumstantial",
            revival_condition="Tier 1 proof insufficient + embedding accepted",
        )
        result = _tier("incremental", claims=[{"past_claim_id": "past-c"}])
        llm = CapturingLLMClient([json.dumps(result)])
        svc = LensService(store, event_svc, repo=repo, llm=llm)

        await svc.assess_taste(CUR_ARTIFACT, CUR_CLAIM, CUR_BODY)

        assert "Tier 1 proof insufficient + embedding accepted" in llm.last_user
