"""Tests for LensService.corpus_graph — Lens 第三刀 / ③ 可查询语料 (Tier 0).

Pure structural projection: ZERO LLM, ZERO persistence, ZERO embedding.
Claim/material nodes + CONFIRMED structural edges (contradicts / grounds),
computed on the fly from existing events. Pending/retracted relations excluded.

Seeded via the real InMemory store/repo + EventService — no network, no model.
"""

from __future__ import annotations

import pytest

from anneal.domain.events import CHALLENGE, GROUND, PARK, VERDICT, make_event
from anneal.domain.models import Artifact, Claim, Material
from anneal.services.event_service import EventService
from anneal.services.lens_service import LensService
from anneal.store.event_store import InMemoryEventStore
from anneal.store.repository import InMemoryRepository


LIB = "lib-1"
OTHER_LIB = "lib-2"


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


@pytest.fixture
def svc(store, event_svc, repo):
    # No LLM injected — corpus_graph must never touch it.
    return LensService(store, event_svc, repo=repo, llm=None)


def _seed_claim(
    repo,
    *,
    claim_id: str,
    artifact_id: str,
    body: str,
    library_id: str = LIB,
) -> Claim:
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


def _lens_contradiction(actor_artifact, store, event_svc, *, current_claim,
                        past_claim, confirm=True):
    """Append a ② lens_contradiction CHALLENGE on the current claim's artifact."""
    ev = make_event(
        type=CHALLENGE, actor="system", confirmed=False, target_ref=current_claim,
        payload={"kind": "lens_contradiction", "past_claim_id": past_claim,
                 "question": "How reconcile?"},
    )
    event_svc.append_event(actor_artifact, ev)
    if confirm:
        event_svc.confirm_event(actor_artifact, ev.id)
    return ev


def _ground(store, event_svc, *, artifact_id, claim_id, material_id, confirm=True):
    ev = make_event(
        type=GROUND, actor="user", confirmed=False, target_ref=claim_id,
        payload={"material_id": material_id, "supported": True},
    )
    event_svc.append_event(artifact_id, ev)
    if confirm:
        event_svc.confirm_event(artifact_id, ev.id)
    return ev


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_confirmed_contradiction_makes_one_edge(store, event_svc, repo, svc):
    _seed_claim(repo, claim_id="c-cur", artifact_id="a-cur", body="X causes Y")
    _seed_claim(repo, claim_id="c-past", artifact_id="a-past", body="X does not cause Y")
    _grill_to_verdict(store, event_svc, artifact_id="a-cur", claim_id="c-cur",
                      outcome="survived")
    _grill_to_verdict(store, event_svc, artifact_id="a-past", claim_id="c-past",
                      outcome="killed")
    _lens_contradiction("a-cur", store, event_svc, current_claim="c-cur",
                        past_claim="c-past", confirm=True)

    graph = svc.corpus_graph(LIB)

    node_ids = {n.id for n in graph.nodes}
    assert node_ids == {"c-cur", "c-past"}
    by_id = {n.id: n for n in graph.nodes}
    assert by_id["c-cur"].type == "claim"
    assert by_id["c-cur"].status == "survived"
    assert by_id["c-past"].status == "killed"

    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert (edge.source, edge.target, edge.type) == ("c-cur", "c-past", "contradicts")


def test_confirmed_ground_makes_material_node_and_edge(store, event_svc, repo, svc):
    _seed_claim(repo, claim_id="c1", artifact_id="a1", body="Claim one")
    _grill_to_verdict(store, event_svc, artifact_id="a1", claim_id="c1",
                      outcome="survived")
    repo.create_material(
        Material(id="m1", library_id=LIB, kind="paper",
                 payload={"title": "Seminal Paper"})
    )
    _ground(store, event_svc, artifact_id="a1", claim_id="c1", material_id="m1",
            confirm=True)

    graph = svc.corpus_graph(LIB)

    by_id = {n.id: n for n in graph.nodes}
    assert by_id["m1"].type == "material"
    assert by_id["m1"].label == "Seminal Paper"
    assert by_id["m1"].status is None
    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert (edge.source, edge.target, edge.type) == ("c1", "m1", "grounds")


def test_pending_contradiction_no_edge(store, event_svc, repo, svc):
    _seed_claim(repo, claim_id="c-cur", artifact_id="a-cur", body="X causes Y")
    _seed_claim(repo, claim_id="c-past", artifact_id="a-past", body="not X->Y")
    _grill_to_verdict(store, event_svc, artifact_id="a-cur", claim_id="c-cur",
                      outcome="survived")
    _grill_to_verdict(store, event_svc, artifact_id="a-past", claim_id="c-past",
                      outcome="survived")
    _lens_contradiction("a-cur", store, event_svc, current_claim="c-cur",
                        past_claim="c-past", confirm=False)

    graph = svc.corpus_graph(LIB)
    assert graph.edges == []
    assert len(graph.nodes) == 2  # nodes still present, just no edge


def test_pending_ground_no_edge_no_material_node(store, event_svc, repo, svc):
    _seed_claim(repo, claim_id="c1", artifact_id="a1", body="Claim one")
    repo.create_material(
        Material(id="m1", library_id=LIB, kind="paper", payload={"title": "P"})
    )
    _ground(store, event_svc, artifact_id="a1", claim_id="c1", material_id="m1",
            confirm=False)

    graph = svc.corpus_graph(LIB)
    assert graph.edges == []
    # Material node only appears for a CONFIRMED ground.
    assert {n.id for n in graph.nodes} == {"c1"}


def test_retracted_contradiction_no_edge(store, event_svc, repo, svc):
    _seed_claim(repo, claim_id="c-cur", artifact_id="a-cur", body="X causes Y")
    _seed_claim(repo, claim_id="c-past", artifact_id="a-past", body="not X->Y")
    _grill_to_verdict(store, event_svc, artifact_id="a-cur", claim_id="c-cur",
                      outcome="survived")
    _grill_to_verdict(store, event_svc, artifact_id="a-past", claim_id="c-past",
                      outcome="survived")
    ev = _lens_contradiction("a-cur", store, event_svc, current_claim="c-cur",
                             past_claim="c-past", confirm=True)
    event_svc.retract_event("a-cur", ev.id)

    graph = svc.corpus_graph(LIB)
    assert graph.edges == []


def test_cross_library_isolation(store, event_svc, repo, svc):
    # Library LIB: c1 -contradicts-> c2
    _seed_claim(repo, claim_id="c1", artifact_id="a1", body="A")
    _seed_claim(repo, claim_id="c2", artifact_id="a2", body="B")
    _grill_to_verdict(store, event_svc, artifact_id="a1", claim_id="c1",
                      outcome="survived")
    _grill_to_verdict(store, event_svc, artifact_id="a2", claim_id="c2",
                      outcome="survived")
    _lens_contradiction("a1", store, event_svc, current_claim="c1",
                        past_claim="c2", confirm=True)

    # OTHER_LIB: its own claim + edge
    _seed_claim(repo, claim_id="o1", artifact_id="oa1", body="O1",
                library_id=OTHER_LIB)
    _seed_claim(repo, claim_id="o2", artifact_id="oa2", body="O2",
                library_id=OTHER_LIB)
    _grill_to_verdict(store, event_svc, artifact_id="oa1", claim_id="o1",
                      outcome="survived")
    _grill_to_verdict(store, event_svc, artifact_id="oa2", claim_id="o2",
                      outcome="survived")
    _lens_contradiction("oa1", store, event_svc, current_claim="o1",
                        past_claim="o2", confirm=True)

    graph = svc.corpus_graph(LIB)
    assert {n.id for n in graph.nodes} == {"c1", "c2"}
    assert all(e.source in {"c1", "c2"} and e.target in {"c1", "c2"}
               for e in graph.edges)
    assert len(graph.edges) == 1


def test_dangling_edge_dropped(store, event_svc, repo, svc):
    # past_claim points to a claim NOT in this library -> drop edge defensively.
    _seed_claim(repo, claim_id="c1", artifact_id="a1", body="A")
    _grill_to_verdict(store, event_svc, artifact_id="a1", claim_id="c1",
                      outcome="survived")
    _lens_contradiction("a1", store, event_svc, current_claim="c1",
                        past_claim="ghost-claim", confirm=True)

    graph = svc.corpus_graph(LIB)
    assert graph.edges == []
    assert {n.id for n in graph.nodes} == {"c1"}


def test_claim_status_variants(store, event_svc, repo, svc):
    _seed_claim(repo, claim_id="s", artifact_id="as", body="survived one")
    _seed_claim(repo, claim_id="k", artifact_id="ak", body="killed one")
    _seed_claim(repo, claim_id="p", artifact_id="ap", body="parked one")
    _seed_claim(repo, claim_id="o", artifact_id="ao", body="open one")
    _grill_to_verdict(store, event_svc, artifact_id="as", claim_id="s",
                      outcome="survived")
    _grill_to_verdict(store, event_svc, artifact_id="ak", claim_id="k",
                      outcome="killed")
    _park_only(store, artifact_id="ap", claim_id="p")
    # 'o' has no events at all -> open

    graph = svc.corpus_graph(LIB)
    by_id = {n.id: n for n in graph.nodes}
    assert by_id["s"].status == "survived"
    assert by_id["k"].status == "killed"
    assert by_id["p"].status == "parked"
    assert by_id["o"].status == "open"


def test_claim_without_artifact_skipped(store, event_svc, repo, svc):
    repo.create_claim(Claim(id="no-art", library_id=LIB, body="orphan",
                            artifact_ids=[]))
    graph = svc.corpus_graph(LIB)
    assert graph.nodes == []
    assert graph.edges == []


def test_determinism_stable_ordering(store, event_svc, repo, svc):
    # Seed several claims/edges; the graph must be byte-stable across calls.
    for i in range(4):
        _seed_claim(repo, claim_id=f"c{i}", artifact_id=f"a{i}", body=f"body {i}")
        _grill_to_verdict(store, event_svc, artifact_id=f"a{i}", claim_id=f"c{i}",
                          outcome="survived")
    _lens_contradiction("a0", store, event_svc, current_claim="c0",
                        past_claim="c1", confirm=True)
    _lens_contradiction("a2", store, event_svc, current_claim="c2",
                        past_claim="c3", confirm=True)

    g1 = svc.corpus_graph(LIB).model_dump(mode="json")
    g2 = svc.corpus_graph(LIB).model_dump(mode="json")
    assert g1 == g2
    node_ids = [n["id"] for n in g1["nodes"]]
    assert node_ids == sorted(node_ids)
    edge_tuples = [(e["source"], e["target"], e["type"]) for e in g1["edges"]]
    assert edge_tuples == sorted(edge_tuples)


def test_empty_library(store, event_svc, repo, svc):
    graph = svc.corpus_graph("nonexistent-lib")
    assert graph.nodes == []
    assert graph.edges == []


# ---------------------------------------------------------------------------
# narrowed_from — deterministic lineage edge from boundary-kill verdicts
# (spec-verdict-precedent §2: 划界死 successor → 语料图免费得确定性边, 非 LLM)
# ---------------------------------------------------------------------------


def _boundary_kill(store, event_svc, *, artifact_id, claim_id, successor_id,
                   confirm=True):
    """Park -> challenge -> kill(boundary, successor). Optionally confirm."""
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
        payload={"outcome": "kill", "rationale": "over-broad",
                 "death_cause": "boundary", "successor_claim_id": successor_id},
    )
    event_svc.append_event(artifact_id, verdict)
    if confirm:
        event_svc.confirm_event(artifact_id, verdict.id)
    return verdict


def test_boundary_kill_with_successor_makes_narrowed_from_edge(
    store, event_svc, repo, svc
):
    _seed_claim(repo, claim_id="c-dead", artifact_id="a-dead", body="broad claim")
    _seed_claim(repo, claim_id="c-narrow", artifact_id="a-narrow", body="narrow claim")
    _boundary_kill(store, event_svc, artifact_id="a-dead", claim_id="c-dead",
                   successor_id="c-narrow")
    _grill_to_verdict(store, event_svc, artifact_id="a-narrow",
                      claim_id="c-narrow", outcome="survived")

    graph = svc.corpus_graph(LIB)

    narrowed = [e for e in graph.edges if e.type == "narrowed_from"]
    assert len(narrowed) == 1
    # direction: successor —narrowed_from→ killed claim
    assert narrowed[0].source == "c-narrow"
    assert narrowed[0].target == "c-dead"


def test_pending_boundary_kill_no_edge(store, event_svc, repo, svc):
    """Unconfirmed verdicts produce no narrowed_from edge (Q-5 discipline)."""
    _seed_claim(repo, claim_id="c-dead", artifact_id="a-dead", body="broad")
    _seed_claim(repo, claim_id="c-narrow", artifact_id="a-narrow", body="narrow")
    _boundary_kill(store, event_svc, artifact_id="a-dead", claim_id="c-dead",
                   successor_id="c-narrow", confirm=False)

    graph = svc.corpus_graph(LIB)
    assert [e for e in graph.edges if e.type == "narrowed_from"] == []


def test_retracted_boundary_kill_no_edge(store, event_svc, repo, svc):
    _seed_claim(repo, claim_id="c-dead", artifact_id="a-dead", body="broad")
    _seed_claim(repo, claim_id="c-narrow", artifact_id="a-narrow", body="narrow")
    verdict = _boundary_kill(store, event_svc, artifact_id="a-dead",
                             claim_id="c-dead", successor_id="c-narrow")
    event_svc.retract_event("a-dead", verdict.id)

    graph = svc.corpus_graph(LIB)
    assert [e for e in graph.edges if e.type == "narrowed_from"] == []


def test_dangling_successor_dropped(store, event_svc, repo, svc):
    """A successor_claim_id pointing outside the Library produces no edge."""
    _seed_claim(repo, claim_id="c-dead", artifact_id="a-dead", body="broad")
    _boundary_kill(store, event_svc, artifact_id="a-dead", claim_id="c-dead",
                   successor_id="c-ghost")

    graph = svc.corpus_graph(LIB)
    assert [e for e in graph.edges if e.type == "narrowed_from"] == []


def test_legacy_kill_verdict_no_successor_no_edge_no_crash(
    store, event_svc, repo, svc
):
    """Legacy kill verdicts (no triage fields) replay cleanly: no edge."""
    _seed_claim(repo, claim_id="c-old", artifact_id="a-old", body="old claim")
    _grill_to_verdict(store, event_svc, artifact_id="a-old", claim_id="c-old",
                      outcome="killed")

    graph = svc.corpus_graph(LIB)
    assert [e for e in graph.edges if e.type == "narrowed_from"] == []
    # the killed node itself still projects
    assert any(n.id == "c-old" and n.status == "killed" for n in graph.nodes)
