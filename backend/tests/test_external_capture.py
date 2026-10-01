"""刀2 part 2b — 定见引用外部文献时摘要快照入「外部捕获」容器(grill Q4/Q5/Q6/Q8/Q12)。"""
import pytest
from fastapi.testclient import TestClient

from cui.api.app import create_native_test_app
from cui.research_universe.api.routes import LibraryContext
from cui.research_universe.api.slice7 import ranked_corpus_hits
from cui.research_universe.application import ChallengeDraft, Slice1Service, universe_home_projection
from cui.research_universe.corpus import EXTERNAL_WS_COMMAND, corpus_workspace_ids, workspace_id_for
from cui.research_universe.domain.events import validate_payload
from cui.research_universe.store.event_store import CommandFingerprintConflict, InMemoryNativeEventStore

EXT_A = {"locator": "arxiv:2504.00001", "excerpt": "Abstract A: RLHF alignment under distribution shift.", "url": "https://arxiv.org/abs/2504.00001"}
EXT_B = {"locator": "https://openalex.org/W123", "excerpt": "Abstract B: preference optimisation survey.", "url": None}


class _Gen:
    def generate(self, *, question, claim):
        return ChallengeDraft("x", "y", "z", "p", "m", ["review_round.question_snapshot"], "low")

    def generate_additional(self, **_): raise AssertionError("unused")

    def generate_literature(self, *, question, claim, materials):
        return ChallengeDraft("overreach", "narrower scope", "check locators", "lit-v1", "m", [m["locator"] for m in materials], "medium")


def _seed():
    store = InMemoryNativeEventStore()
    universe = store.create_active_universe("lib")
    service = Slice1Service(store, "local", _Gen())
    wid = service.create_workspace(universe, "w1", 0, "Why does RLHF help?").result_payload["workspace_id"]
    cid = service.create_claim(universe, wid, "c1", 0, "RLHF helps reasoning.").result_payload["claim_id"]
    rid = service.start_review_round(universe, cid, "r1", 0).result_payload["review_round_id"]
    return store, universe, service, wid, rid


def _captured(store, universe):
    cap = workspace_id_for(EXTERNAL_WS_COMMAND)
    return [e.validated_payload() for e in store.read_events(universe) if e.event_type == "material_added" and e.validated_payload().workspace_id == cap]


def test_literature_challenge_all_external_captures_abstract_snapshots():
    store, universe, service, wid, rid = _seed()
    service.generate_literature_challenge(universe, rid, [], "lit1", 0, externals=[EXT_A, EXT_B])
    mats = _captured(store, universe)
    assert sorted(m.source_locator for m in mats) == sorted([EXT_A["locator"], EXT_B["locator"]])
    assert all(m.content_scope == "abstract" and m.purpose == "evidence" and m.parse_status == "parsed" for m in mats)
    assert {m.source_locator: m.excerpt for m in mats}[EXT_A["locator"]] == EXT_A["excerpt"]
    ch = [e for e in store.read_events(universe) if e.event_type == "challenge_created"][-1].validated_payload()
    assert set(ch.basis_refs) == {m.source_locator for m in mats}
    # 容器 workspace 只创建一次,且与 challenge 同一次提交
    assert sum(1 for e in store.read_events(universe) if e.event_type == "workspace_created" and e.validated_payload().workspace_id == workspace_id_for(EXTERNAL_WS_COMMAND)) == 1


def test_second_challenge_reuses_material_no_duplicate():
    store, universe, service, wid, rid = _seed()
    service.generate_literature_challenge(universe, rid, [], "lit1", 0, externals=[EXT_A])
    before = len([e for e in store.read_events(universe) if e.event_type == "material_added"])
    service.generate_literature_challenge(universe, rid, [], "lit2", 0, externals=[EXT_A, EXT_B])
    mats = _captured(store, universe)
    assert [m.source_locator for m in mats].count(EXT_A["locator"]) == 1
    assert len(mats) == 2 and len([e for e in store.read_events(universe) if e.event_type == "material_added"]) == before + 1


def test_literature_challenge_idempotent_retry_and_fingerprint_conflict():
    store, universe, service, wid, rid = _seed()
    first = service.generate_literature_challenge(universe, rid, [], "lit1", 0, externals=[EXT_A])
    n = len(store.read_events(universe))
    again = service.generate_literature_challenge(universe, rid, [], "lit1", 0, externals=[EXT_A])
    assert again.replayed and again.event_ids == first.event_ids and len(store.read_events(universe)) == n
    with pytest.raises(CommandFingerprintConflict):
        service.generate_literature_challenge(universe, rid, [], "lit1", 0, externals=[EXT_A, EXT_B])


def test_retry_idempotent_even_when_locator_captured_by_other_command():
    # 首次提交里 EXT_A 是新快照;之后别的命令又引用 → 复用。首次命令重试仍须幂等。
    store, universe, service, wid, rid = _seed()
    first = service.generate_literature_challenge(universe, rid, [], "lit1", 0, externals=[EXT_A])
    service.generate_literature_challenge(universe, rid, [], "lit2", 0, externals=[EXT_A])
    assert service.generate_literature_challenge(universe, rid, [], "lit1", 0, externals=[EXT_A]).event_ids == first.event_ids
    # lit2 当初全复用(无新快照),重试亦幂等
    assert service.generate_literature_challenge(universe, rid, [], "lit2", 0, externals=[EXT_A]).replayed


def test_gap_propose_with_external_refs_captures_and_idempotent():
    store, universe, service, wid, rid = _seed()
    args = (universe, wid, "现有文献覆盖了机制,但没有覆盖真实任务上的边界。", "q", "active", [EXT_A["locator"]], "请指出反例。", "2026-10-02", "g1", 0)
    first = service.propose_gap_candidate(*args, externals=[EXT_A])
    mats = _captured(store, universe)
    assert [m.source_locator for m in mats] == [EXT_A["locator"]] and mats[0].content_scope == "abstract"
    gap = [e for e in store.read_events(universe) if e.event_type == "gap_candidate_proposed"][-1].validated_payload()
    assert gap.matched_locators == [EXT_A["locator"]]
    assert service.propose_gap_candidate(*args, externals=[EXT_A]).event_ids == first.event_ids
    with pytest.raises(CommandFingerprintConflict):
        service.propose_gap_candidate(*args, externals=[EXT_A, EXT_B])


def test_gap_http_external_refs_and_claim_kind_roundtrip():
    store = InMemoryNativeEventStore()
    universe = store.create_active_universe("lib")
    service = Slice1Service(store, "local", _Gen())
    wid = service.create_workspace(universe, "w1", 0, "Q?").result_payload["workspace_id"]
    client = TestClient(create_native_test_app(store, LibraryContext("lib"), principal=None, challenge_generator=_Gen()))
    r = client.post(f"/api/v2/workspaces/{wid}/gap-candidates", json={
        "command_id": "g1", "expected_sequence": 0, "coverage_statement": "覆盖了机制但缺少真实任务边界。", "search_query": "q",
        "matched_locators": [EXT_A["locator"]], "counterexample_invitation": "请指出反例", "external_refs": [EXT_A]})
    assert r.status_code == 201, r.text
    assert [m.source_locator for m in _captured(store, universe)] == [EXT_A["locator"]]
    for kind, expect in (("division", "division"), (None, None)):
        body = {"command_id": f"c-{kind}", "expected_sequence": 0, "text": "some claim"}
        if kind: body["kind"] = kind
        assert client.post(f"/api/v2/workspaces/{wid}/claims", json=body).status_code == 201
        assert [e.validated_payload().kind for e in store.read_events(universe) if e.event_type == "claim_created"][-1] == expect
    assert client.post(f"/api/v2/workspaces/{wid}/claims", json={"command_id": "bad", "expected_sequence": 0, "text": "t", "kind": "custom"}).status_code == 422


def test_old_events_without_new_fields_still_validate():
    m = validate_payload("material_added", 1, {"material_id": "m", "workspace_id": "w", "excerpt": "e", "source_locator": "arxiv:1", "parse_status": "parsed", "purpose": "evidence"})
    assert m.content_scope == "full"
    c = validate_payload("claim_created", 1, {"claim_id": "c", "origin_workspace_id": "w", "claim_version_id": "v", "claim_text": "t"})
    assert c.kind is None


def test_corpus_search_active_finds_captured_paper_and_home_excludes_container():
    store, universe, service, wid, rid = _seed()
    service.generate_literature_challenge(universe, rid, [], "lit1", 0, externals=[EXT_A])
    hits = ranked_corpus_hits(store, universe, "active", "distribution shift", 10)
    assert [h.source_locator for h in hits] == [EXT_A["locator"]]
    assert ranked_corpus_hits(store, universe, "legacy", "distribution shift", 10) == []
    assert workspace_id_for(EXTERNAL_WS_COMMAND) in corpus_workspace_ids()
    home = universe_home_projection(store, universe)
    assert [w["id"] for w in home["workspaces"]] == [wid]
