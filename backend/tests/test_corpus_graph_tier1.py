"""Tests for Lens 第三刀 / ③ 可查询语料 — Tier 1 (persistent semantic graph).

LLM-computed typed edges (builds_on / depends_on / shares_method / shares_gap)
are persisted as confirmed ``LINK`` events (NO new table/store/embedding) and
read back by the corpus_graph projection (which stays a PURE READ).

Edges are born confirmed=True + retractable; only grilled claims participate
(只吃 grilled trajectory). Seeded via the real InMemory store/repo + EventService
with a FakeLLM — no network, no real model.
"""

from __future__ import annotations

import json

import pytest

from anneal.domain.events import CHALLENGE, LINK, PARK, VERDICT, make_event
from anneal.domain.models import Artifact, Claim
from anneal.llm.errors import LLMNotConfiguredError
from anneal.services.event_service import EventService
from anneal.services.lens_service import LensService
from anneal.store.event_store import InMemoryEventStore
from anneal.store.repository import InMemoryRepository
from tests.fakes import FakeLLMClient


LIB = "lib-1"


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


def _svc(store, event_svc, repo, responses=None):
    llm = (
        FakeLLMClient([json.dumps(r) for r in responses])
        if responses is not None
        else None
    )
    return LensService(store, event_svc, repo=repo, llm=llm)


def _seed_claim(repo, *, claim_id, artifact_id, body, library_id=LIB):
    repo.create_artifact(
        Artifact(id=artifact_id, library_id=library_id, kind="idea", goal="g")
    )
    claim = Claim(
        id=claim_id, library_id=library_id, body=body, artifact_ids=[artifact_id]
    )
    repo.create_claim(claim)
    return claim


def _grill_to_verdict(store, event_svc, *, artifact_id, claim_id, outcome):
    """Park -> challenge -> confirmed verdict so claim_status is survived/killed."""
    store.append(
        artifact_id,
        make_event(type=PARK, actor="user", confirmed=True, target_ref=claim_id,
                   payload={"kind": "idea"}),
    )
    store.append(
        artifact_id,
        make_event(type=CHALLENGE, actor="system", confirmed=True,
                   target_ref=claim_id, payload={"question": "q"}),
    )
    verdict = make_event(
        type=VERDICT, actor="system", confirmed=False, target_ref=claim_id,
        payload={"outcome": "survive" if outcome == "survived" else "kill"},
    )
    event_svc.append_event(artifact_id, verdict)
    event_svc.confirm_event(artifact_id, verdict.id)


def _park_only(store, *, artifact_id, claim_id):
    store.append(
        artifact_id,
        make_event(type=PARK, actor="user", confirmed=True, target_ref=claim_id,
                   payload={"kind": "idea"}),
    )


# Bodies share topic terms so the lexical prefilter keeps them as candidates.
BODY_A = "Transformer attention improves protein folding prediction accuracy"
BODY_B = "Transformer attention models also improve protein structure prediction"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_builds_on_edge_persisted_and_in_graph(store, event_svc, repo):
    """Fake LLM returns a builds_on edge between two grilled claims -> a confirmed
    LINK event is appended AND corpus_graph shows the builds_on edge."""
    _seed_claim(repo, claim_id="c-a", artifact_id="a-a", body=BODY_A)
    _seed_claim(repo, claim_id="c-b", artifact_id="a-b", body=BODY_B)
    _grill_to_verdict(store, event_svc, artifact_id="a-a", claim_id="c-a",
                      outcome="survived")
    _grill_to_verdict(store, event_svc, artifact_id="a-b", claim_id="c-b",
                      outcome="survived")

    # One claim (whichever the service hits first) yields a builds_on edge; the
    # other yields none. Provide a response set that always answers correctly.
    svc = _svc(store, event_svc, repo, responses=[
        {"edges": [{"target_claim_id": "c-b", "edge_type": "builds_on",
                    "reason": "extends the folding result"}]},
        {"edges": [{"target_claim_id": "c-a", "edge_type": "builds_on",
                    "reason": "extends the folding result"}]},
    ])

    created = await svc.compute_semantic_edges(LIB)

    assert len(created) >= 1
    link = created[0]
    assert link.type == LINK
    assert link.confirmed is True
    assert link.payload["edge_type"] == "builds_on"
    assert link.payload["auto_generated"] is True
    assert link.payload["source_claim_id"] == link.target_ref
    # source/target are the two grilled claims.
    assert {link.payload["source_claim_id"], link.payload["target_claim_id"]} == {
        "c-a", "c-b"
    }

    graph = svc.corpus_graph(LIB)
    builds = [e for e in graph.edges if e.type == "builds_on"]
    assert len(builds) >= 1
    assert builds[0].source == link.payload["source_claim_id"]
    assert builds[0].target == link.payload["target_claim_id"]


async def test_compute_once_idempotent(store, event_svc, repo):
    """Calling compute_semantic_edges twice does not duplicate edges."""
    _seed_claim(repo, claim_id="c-a", artifact_id="a-a", body=BODY_A)
    _seed_claim(repo, claim_id="c-b", artifact_id="a-b", body=BODY_B)
    _grill_to_verdict(store, event_svc, artifact_id="a-a", claim_id="c-a",
                      outcome="survived")
    _grill_to_verdict(store, event_svc, artifact_id="a-b", claim_id="c-b",
                      outcome="survived")

    svc = _svc(store, event_svc, repo, responses=[
        {"edges": [{"target_claim_id": "c-b", "edge_type": "builds_on",
                    "reason": "r"}]},
        {"edges": [{"target_claim_id": "c-a", "edge_type": "builds_on",
                    "reason": "r"}]},
    ])

    first = await svc.compute_semantic_edges(LIB)
    second = await svc.compute_semantic_edges(LIB)

    assert len(first) >= 1
    assert second == []  # already-linked pairs skipped

    # No duplicate LINK events in the store.
    all_links = [
        e for aid in ("a-a", "a-b") for e in store.get_events(aid)
        if e.type == LINK
    ]
    pairs = [(e.payload["source_claim_id"], e.payload["target_claim_id"])
             for e in all_links]
    assert len(pairs) == len(set(pairs))


async def test_hallucinated_target_dropped(store, event_svc, repo):
    """A target_claim_id that is not a candidate -> no LINK event."""
    _seed_claim(repo, claim_id="c-a", artifact_id="a-a", body=BODY_A)
    _seed_claim(repo, claim_id="c-b", artifact_id="a-b", body=BODY_B)
    _grill_to_verdict(store, event_svc, artifact_id="a-a", claim_id="c-a",
                      outcome="survived")
    _grill_to_verdict(store, event_svc, artifact_id="a-b", claim_id="c-b",
                      outcome="survived")

    svc = _svc(store, event_svc, repo, responses=[
        {"edges": [{"target_claim_id": "ghost", "edge_type": "builds_on",
                    "reason": "invented"}]},
    ])

    created = await svc.compute_semantic_edges(LIB)
    assert created == []
    graph = svc.corpus_graph(LIB)
    assert all(e.type in ("contradicts", "grounds") for e in graph.edges)
    assert [e for e in graph.edges if e.type == "builds_on"] == []


async def test_invalid_edge_type_dropped(store, event_svc, repo):
    """An edge_type outside the four legal types -> dropped."""
    _seed_claim(repo, claim_id="c-a", artifact_id="a-a", body=BODY_A)
    _seed_claim(repo, claim_id="c-b", artifact_id="a-b", body=BODY_B)
    _grill_to_verdict(store, event_svc, artifact_id="a-a", claim_id="c-a",
                      outcome="survived")
    _grill_to_verdict(store, event_svc, artifact_id="a-b", claim_id="c-b",
                      outcome="survived")

    svc = _svc(store, event_svc, repo, responses=[
        {"edges": [{"target_claim_id": "c-b", "edge_type": "supersedes",
                    "reason": "bogus type"}]},
    ])

    created = await svc.compute_semantic_edges(LIB)
    assert created == []


async def test_parked_and_open_claims_get_no_edges(store, event_svc, repo):
    """Only grilled claims participate; PARK/open claims never get edges."""
    _seed_claim(repo, claim_id="c-grilled", artifact_id="a-g", body=BODY_A)
    _seed_claim(repo, claim_id="c-parked", artifact_id="a-p", body=BODY_B)
    _seed_claim(repo, claim_id="c-open", artifact_id="a-o", body=BODY_B)
    _grill_to_verdict(store, event_svc, artifact_id="a-g", claim_id="c-grilled",
                      outcome="survived")
    _park_only(store, artifact_id="a-p", claim_id="c-parked")
    # c-open has no events at all.

    # If the LLM were (wrongly) asked, it would try to connect — but parked/open
    # claims are never candidates, so this response must never fire usefully.
    svc = _svc(store, event_svc, repo, responses=[
        {"edges": [{"target_claim_id": "c-parked", "edge_type": "builds_on",
                    "reason": "should never happen"}]},
    ])

    created = await svc.compute_semantic_edges(LIB)
    assert created == []
    graph = svc.corpus_graph(LIB)
    assert [e for e in graph.edges if e.type == "builds_on"] == []


async def test_retracted_link_drops_edge_from_graph(store, event_svc, repo):
    """A retracted LINK event -> its edge disappears from corpus_graph."""
    _seed_claim(repo, claim_id="c-a", artifact_id="a-a", body=BODY_A)
    _seed_claim(repo, claim_id="c-b", artifact_id="a-b", body=BODY_B)
    _grill_to_verdict(store, event_svc, artifact_id="a-a", claim_id="c-a",
                      outcome="survived")
    _grill_to_verdict(store, event_svc, artifact_id="a-b", claim_id="c-b",
                      outcome="survived")

    svc = _svc(store, event_svc, repo, responses=[
        {"edges": [{"target_claim_id": "c-b", "edge_type": "builds_on",
                    "reason": "r"}]},
        {"edges": [{"target_claim_id": "c-a", "edge_type": "builds_on",
                    "reason": "r"}]},
    ])

    created = await svc.compute_semantic_edges(LIB)
    assert created  # at least one builds_on LINK
    assert [e for e in svc.corpus_graph(LIB).edges if e.type == "builds_on"]

    # Retract every LINK; each lives on its source claim's artifact
    # (target_ref = source_claim_id). The edges then drop via existing machinery.
    for link in created:
        source_artifact = _artifact_of(repo, link.payload["source_claim_id"])
        event_svc.retract_event(source_artifact, link.id)

    graph = svc.corpus_graph(LIB)
    assert [e for e in graph.edges if e.type == "builds_on"] == []


def _artifact_of(repo, claim_id):
    for lib_claim in repo.list_claims(LIB):
        if lib_claim.id == claim_id:
            return lib_claim.artifact_ids[0]
    raise AssertionError(f"no artifact for {claim_id}")


async def test_llm_none_raises(store, event_svc, repo):
    svc = _svc(store, event_svc, repo, responses=None)
    with pytest.raises(LLMNotConfiguredError):
        await svc.compute_semantic_edges(LIB)


async def test_tier0_edges_still_work_alongside_semantic(store, event_svc, repo):
    """corpus_graph still returns contradicts/grounds edges alongside builds_on."""
    _seed_claim(repo, claim_id="c-a", artifact_id="a-a", body=BODY_A)
    _seed_claim(repo, claim_id="c-b", artifact_id="a-b", body=BODY_B)
    _grill_to_verdict(store, event_svc, artifact_id="a-a", claim_id="c-a",
                      outcome="survived")
    _grill_to_verdict(store, event_svc, artifact_id="a-b", claim_id="c-b",
                      outcome="survived")

    # A confirmed Tier 0 contradiction edge c-a -> c-b.
    contra = make_event(
        type=CHALLENGE, actor="system", confirmed=False, target_ref="c-a",
        payload={"kind": "lens_contradiction", "past_claim_id": "c-b",
                 "question": "?"},
    )
    event_svc.append_event("a-a", contra)
    event_svc.confirm_event("a-a", contra.id)

    svc = _svc(store, event_svc, repo, responses=[
        {"edges": [{"target_claim_id": "c-b", "edge_type": "shares_method",
                    "reason": "same transformer approach"}]},
        {"edges": []},
    ])

    await svc.compute_semantic_edges(LIB)

    graph = svc.corpus_graph(LIB)
    types = {e.type for e in graph.edges}
    assert "contradicts" in types
    assert "shares_method" in types
