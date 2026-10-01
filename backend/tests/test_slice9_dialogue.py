"""slice1 second cut — literature challenge + dialogue transient endpoints."""
import json

import pytest
from cui.research_universe.api import slice9 as slice9_module
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cui.research_universe.application import ChallengeDraft, Slice1Service
from cui.research_universe.challenge_generator import (
    PROMPT_VERSION_LITERATURE,
    RealChallengeGenerator,
    format_materials_block,
)
from cui.research_universe.api.routes import LibraryContext
from cui.research_universe.api.slice9 import create_dialogue_router
from cui.research_universe.store.event_store import InMemoryNativeEventStore
from tests.fakes import CapturingLLMClient


class _LitGen:
    def generate(self, *, question, claim):
        return ChallengeDraft("g", "w", "s", "slice1-narrow-challenge-v1", "m", ["review_round.question_snapshot", "review_round.claim_snapshot"], "low")

    def generate_additional(self, **kwargs):
        raise AssertionError("unused")

    def generate_literature(self, *, question, claim, materials):
        return ChallengeDraft(
            "the claim overreaches what these papers show",
            "the cited corpus supports a narrower scope",
            "restate the claim to the supported scope and check each locator",
            PROMPT_VERSION_LITERATURE, "m", [m["locator"] for m in materials], "medium",
        )


class _PlainGen(_LitGen):
    def generate_literature(self, **kwargs):
        raise AssertionError("should not be used")


def _seed(gen=None):
    store = InMemoryNativeEventStore()
    universe = store.create_active_universe("lib")
    service = Slice1Service(store, "local", gen or _LitGen())
    wid = service.create_workspace(universe, "w1", 0, "Why does RLHF improve reasoning?").result_payload["workspace_id"]
    mat = service.add_material(universe, wid, "# RLHF and reasoning\n\nRLHF improves instruction following in evaluations.", "arxiv:2401.00001", "parsed", "evidence", "m1", 0).result_payload["material_id"]
    cid = service.create_claim(universe, wid, "c1", 0, "RLHF improves reasoning because it aligns preferences.").result_payload["claim_id"]
    rid = service.start_review_round(universe, cid, "r1", 0).result_payload["review_round_id"]
    return store, universe, service, wid, mat, rid


def test_format_materials_block_truncates_and_labels():
    block = format_materials_block([{"locator": "arxiv:2401.00001", "excerpt": "x" * 5000}])
    assert block.startswith("- [arxiv:2401.00001] ")
    assert len(block) < 2000
    with pytest.raises(ValueError):
        format_materials_block([])


def test_generate_literature_passes_locators_and_version():
    raw = json.dumps({"attack_surface": "a", "why_it_matters": "w", "self_check_method": "s", "uncertainty": 0.3})
    client = CapturingLLMClient([raw])
    gen = RealChallengeGenerator(client, "m1")
    draft = gen.generate_literature(question="q?", claim="c.", materials=[{"locator": "arxiv:2401.00001", "excerpt": "body"}])
    assert draft.prompt_version == PROMPT_VERSION_LITERATURE
    assert draft.basis_refs == ["arxiv:2401.00001"]
    assert "arxiv:2401.00001" in client.last_user


def test_service_literature_challenge_commits_event_with_basis():
    store, universe, service, wid, mat, rid = _seed()
    result = service.generate_literature_challenge(universe, rid, [mat], "lit1", 0)
    assert result.replayed is False
    events = [e for e in store.read_events(universe) if e.event_type == "challenge_created"]
    challenge = events[-1].validated_payload()
    assert challenge.prompt_version == PROMPT_VERSION_LITERATURE
    assert "arxiv:2401.00001" in challenge.basis_refs
    assert challenge.generator_kind == "system"


def test_service_literature_challenge_rejects_foreign_material():
    store, universe, service, wid, mat, rid = _seed()
    other = service.create_workspace(universe, "w2", 0, "other").result_payload["workspace_id"]
    foreign = service.add_material(universe, other, "foreign body", "doi:10.1/x", "parsed", "evidence", "m2", 0).result_payload["material_id"]
    from cui.research_universe.application import BoundaryViolation
    with pytest.raises(BoundaryViolation):
        service.generate_literature_challenge(universe, rid, [foreign], "lit2", 0)


def test_http_literature_challenge_endpoint_round_trip():
    store, universe, service, wid, mat, rid = _seed()
    app = FastAPI()
    app.include_router(create_dialogue_router(service, store, LibraryContext("lib"), None), prefix="/api/v2")
    client = TestClient(app)
    resp = client.post(f"/api/v2/review-rounds/{rid}/literature-challenges",
                       json={"command_id": "lit-http", "expected_sequence": 0, "material_ids": [mat]})
    assert resp.status_code == 201, resp.text
    fragment = resp.json()["fragment"]
    lit = [c for c in fragment["challenges"] if c.get("provenance", {}).get("prompt_version") == PROMPT_VERSION_LITERATURE]
    assert lit and "arxiv:2401.00001" in lit[0]["provenance"]["basis_refs"]


def test_transient_endpoints_need_client_and_work_with_fake():
    store, universe, service, wid, mat, rid = _seed()
    # no client -> 503
    app_no = FastAPI()
    app_no.include_router(create_dialogue_router(service, store, LibraryContext("lib"), None), prefix="/api/v2")
    no_client = TestClient(app_no)
    assert no_client.post(f"/api/v2/workspaces/{wid}/dialogue/landscape-summary", json={"material_ids": [mat]}).status_code == 503
    # standalone router with a fake LLM
    class _Fake:
        def __init__(self, texts): self.texts = texts
        def complete(self, system, user): return self.texts.pop(0)
        def complete_json(self, system, user, retries=2): raise AssertionError("unused")
    fake = _Fake([
        "## 这几篇覆盖了什么\nRLHF 评测覆盖了指令遵循。",
        json.dumps({"coverage_statement": "文献覆盖了评测方法,但没有覆盖推理链上的真实应用缺口。", "counterexample_invitation": "如有推理任务上的 RLHF 数据请指正。"}),
        "Related work paragraph body with [arxiv:2401.00001].",
    ])
    app = FastAPI()
    app.include_router(create_dialogue_router(service, store, LibraryContext("lib"), None, client=fake), prefix="/api/v2")
    client = TestClient(app)
    summary = client.post(f"/api/v2/workspaces/{wid}/dialogue/landscape-summary", json={"material_ids": [mat]})
    assert summary.status_code == 200 and "覆盖" in summary.json()["text"]
    draft = client.post(f"/api/v2/workspaces/{wid}/dialogue/gap-draft", json={"material_ids": [mat]})
    assert draft.status_code == 200 and "coverage_statement" in draft.json()
    rw = client.post(f"/api/v2/workspaces/{wid}/dialogue/related-work-draft", json={"material_ids": [mat], "gap_ids": []})
    assert rw.status_code == 200 and "Related work" in rw.json()["text"]


def test_dialogue_unknown_material_404():
    store, universe, service, wid, mat, rid = _seed()
    fake = type("F", (), {"complete": lambda self, s, u: "x", "complete_json": lambda self, s, u, retries=2: {}})()
    app = FastAPI()
    app.include_router(create_dialogue_router(service, store, LibraryContext("lib"), None, client=fake), prefix="/api/v2")
    resp = TestClient(app).post(f"/api/v2/workspaces/{wid}/dialogue/landscape-summary", json={"material_ids": ["nope"]})
    assert resp.status_code == 404

async def _no_external(query, per_source=5):
    return []


def test_literature_search_endpoint_picks_valid_locators_only(monkeypatch):
    monkeypatch.setattr(slice9_module, "external_search", _no_external)
    store, universe, service, wid, mat, rid = _seed()
    # seed corpus-style materials in the active corpus workspace for ranking
    from cui.tools.v4_importer import ACTIVE_WS_COMMAND, workspace_id_for
    service.create_workspace(universe, ACTIVE_WS_COMMAND, 0, "corpus q")
    cws = workspace_id_for(ACTIVE_WS_COMMAND)
    service.add_material(universe, cws, "# RLHF reasoning paper\n\nRLHF improves reasoning by preference alignment.", "arxiv:2401.00009", "parsed", "evidence", "corp1", 0)
    service.add_material(universe, cws, "# Unrelated cooking paper\n\nRecipes and heat control.", "arxiv:2401.00010", "parsed", "evidence", "corp2", 0)
    fake = type("F", (), {
        "complete": lambda self, system, user: "x",
        "complete_json": lambda self, system, user, retries=2: {"query": "rlhf reasoning", "results": [
            {"locator": "arxiv:2401.00009", "reason": "直接相关"},
            {"locator": "arxiv:9999.99999", "reason": "不在候选中,应被过滤"},
        ]},
    })()
    app = FastAPI()
    app.include_router(create_dialogue_router(service, store, LibraryContext("lib"), None, client=fake), prefix="/api/v2")
    resp = TestClient(app).post(f"/api/v2/workspaces/{wid}/dialogue/literature-search", json={"question": "RLHF 是否提升推理?", "query": "rlhf"})
    assert resp.status_code == 200
    body = resp.json()
    locators = [c["locator"] for c in body["candidates"]]
    assert locators == ["arxiv:2401.00009"]
    assert body["candidates"][0]["material_id"]
    assert body["candidates"][0]["source"] == "corpus"
    assert body["executed_queries"] == ["rlhf"] and body["suggested_query"] == "rlhf reasoning"


def test_gap_draft_does_not_require_or_invent_search_query():
    store, universe, service, wid, mat, rid = _seed()
    fake = type("F", (), {"complete": lambda self, s, u: '{"coverage_statement": "文献覆盖了评测方法,但缺推理应用的缺口。", "counterexample_invitation": "c"}', "complete_json": lambda self, s, u, retries=2: {}})()
    app = FastAPI()
    app.include_router(create_dialogue_router(service, store, LibraryContext("lib"), None, client=fake), prefix="/api/v2")
    resp = TestClient(app).post(f"/api/v2/workspaces/{wid}/dialogue/gap-draft", json={"material_ids": [mat]})
    assert resp.status_code == 200, resp.text
    assert "search_query" not in resp.json()


def test_corpus_materials_allowed_in_any_workspace_dialogue_and_challenge():
    from cui.research_universe.corpus import ACTIVE_WS_COMMAND, workspace_id_for
    store = InMemoryNativeEventStore()
    universe = store.create_active_universe("lib")
    service = Slice1Service(store, "local", _LitGen())
    wid = service.create_workspace(universe, "my-q", 0, "我的问题:RLHF?").result_payload["workspace_id"]
    corpus = service.create_workspace(universe, ACTIVE_WS_COMMAND, 0, "corpus q").result_payload["workspace_id"]
    mat = service.add_material(universe, corpus, "# corpus paper\n\nRLHF aligns preferences.", "arxiv:2401.00077", "parsed", "evidence", "corp-m", 0).result_payload["material_id"]
    # landscape-summary in the NON-corpus workspace may read the corpus material
    fake = type("F", (), {"complete": lambda self, s2, u: "## 覆盖\nRLHF 对齐评测", "complete_json": lambda self, s2, u, retries=2: {}})()
    app = FastAPI()
    app.include_router(create_dialogue_router(service, store, LibraryContext("lib"), None, client=fake), prefix="/api/v2")
    client = TestClient(app)
    resp = client.post(f"/api/v2/workspaces/{wid}/dialogue/landscape-summary", json={"material_ids": [mat]})
    assert resp.status_code == 200, resp.text
    # literature challenge from a round in the non-corpus workspace may cite the corpus material
    cid = service.create_claim(universe, wid, "c-x", 0, "RLHF 提升推理.").result_payload["claim_id"]
    rid = service.start_review_round(universe, cid, "r-x", 0).result_payload["review_round_id"]
    result = service.generate_literature_challenge(universe, rid, [mat], "lit-x", 0)
    assert result.replayed is False
    event = [e for e in store.read_events(universe) if e.event_type == "challenge_created"][-1].validated_payload()
    assert "arxiv:2401.00077" in event.basis_refs


def test_orientation_endpoint_returns_hypotheses_and_keywords():
    store, universe, service, wid, mat, rid = _seed()
    fake = type("F", (), {
        "complete": lambda self, s2, u: "x",
        "complete_json": lambda self, s2, u, retries=2: {"hypotheses": ["RLHF 改善推理是通过偏好对齐减少分布外漂移", "推理提升只是评测过拟合的假象"], "keywords": ["RLHF", "reasoning evaluation", "偏好对齐"]},
    })()
    app = FastAPI()
    app.include_router(create_dialogue_router(service, store, LibraryContext("lib"), None, client=fake), prefix="/api/v2")
    resp = TestClient(app).post(f"/api/v2/workspaces/{wid}/dialogue/orientation", json={"question": "RLHF 是否提升推理?"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["hypotheses"]) == 2 and body["keywords"][0] == "RLHF"


async def _canned_external(query, per_source=5):
    return [{"locator": "arxiv:2504.09999", "title": "External RLHF survey", "excerpt": "external abstract text for RLHF reasoning evaluation.", "url": "https://arxiv.org/abs/2504.09999", "source": "arxiv"}]


def test_literature_search_merges_external_candidates(monkeypatch):
    monkeypatch.setattr(slice9_module, "external_search", _canned_external)
    store, universe, service, wid, mat, rid = _seed()
    fake = type("F", (), {
        "complete": lambda self, s2, u: "x",
        "complete_json": lambda self, s2, u, retries=2: {"query": "rlhf", "results": [{"locator": "arxiv:2504.09999", "reason": "外部综述直接相关"}]},
    })()
    app = FastAPI()
    app.include_router(create_dialogue_router(service, store, LibraryContext("lib"), None, client=fake), prefix="/api/v2")
    resp = TestClient(app).post(f"/api/v2/workspaces/{wid}/dialogue/literature-search", json={"question": "RLHF 推理?", "query": "rlhf"})
    assert resp.status_code == 200
    candidate = resp.json()["candidates"][0]
    assert candidate["locator"] == "arxiv:2504.09999"
    assert candidate["source"] == "arxiv"
    assert candidate["material_id"] is None
    assert candidate["excerpt"] and candidate["url"]


def test_external_refs_flow_through_summary_and_challenge(monkeypatch):
    store, universe, service, wid, mat, rid = _seed()
    fake = type("F", (), {"complete": lambda self, s2, u: "## 覆盖\n外部文献覆盖了 RLHF 对齐。", "complete_json": lambda self, s2, u, retries=2: {}})()
    app = FastAPI()
    app.include_router(create_dialogue_router(service, store, LibraryContext("lib"), None, client=fake), prefix="/api/v2")
    client = TestClient(app)
    ext = [{"locator": "doi:10.1000/example123", "excerpt": "external abstract here for RLHF alignment review.", "url": "https://doi.org/10.1000/example123"}]
    summary = client.post(f"/api/v2/workspaces/{wid}/dialogue/landscape-summary", json={"external_refs": ext})
    assert summary.status_code == 200 and "外部文献" in summary.json()["text"]
    challenge = client.post(f"/api/v2/review-rounds/{rid}/literature-challenges", json={
        "command_id": "lit-ext-http", "expected_sequence": 0, "material_ids": [mat], "external_refs": ext})
    assert challenge.status_code == 201, challenge.text
    lit = [c for c in challenge.json()["fragment"]["challenges"] if c.get("provenance", {}).get("prompt_version") == PROMPT_VERSION_LITERATURE][-1]
    assert "doi:10.1000/example123" in lit["provenance"]["basis_refs"]


def test_cjk_question_translates_query_for_external_sources(monkeypatch):
    captured: dict = {}
    async def _capture_external(query, per_source=5):
        captured["query"] = query
        return [{"locator": "doi:10.1000/hegemony-test", "title": "US Hegemony review", "excerpt": "hegemony global order abstract.", "url": "https://doi.org/10.1000/hegemony-test", "source": "openalex"}]
    monkeypatch.setattr(slice9_module, "external_search", _capture_external)
    store, universe, service, wid, mat, rid = _seed()
    calls = {"n": 0}
    def fake_complete_json(self, system, user, retries=2):
        calls["n"] += 1
        if "query_en" in system:
            return {"query_en": "US hegemony international order"}
        return {"query": "美国霸权", "results": [{"locator": "doi:10.1000/hegemony-test", "reason": "直接相关"}]}
    fake = type("F", (), {"complete": lambda self, s2, u: "x", "complete_json": fake_complete_json})()
    app = FastAPI()
    app.include_router(create_dialogue_router(service, store, LibraryContext("lib"), None, client=fake), prefix="/api/v2")
    resp = TestClient(app).post(f"/api/v2/workspaces/{wid}/dialogue/literature-search", json={"question": "为什么美国最强大?", "query": "美国霸权"})
    assert resp.status_code == 200
    assert captured.get("query") == "US hegemony international order"
    body = resp.json()
    assert body["executed_queries"] == [captured["query"]]  # S20: 记录的是实际执行的(翻译后)检索,不是 LLM 建议词
    assert body["suggested_query"] == "美国霸权"
    candidates = body["candidates"]
    assert candidates and candidates[0]["locator"] == "doi:10.1000/hegemony-test"


def test_literature_challenge_accepts_external_refs_only():
    """外部检索是主路径:全选 arXiv/OpenAlex 候选时 material_ids 为空,不能被 schema 拦掉。"""
    store, universe, service, wid, mat, rid = _seed()
    app = FastAPI()
    app.include_router(create_dialogue_router(service, store, LibraryContext("lib"), None, client=None), prefix="/api/v2")
    client = TestClient(app)
    ext = [{"locator": "doi:10.1000/only-external", "excerpt": "external abstract on RLHF alignment tax.", "url": None}]
    ok = client.post(f"/api/v2/review-rounds/{rid}/literature-challenges", json={
        "command_id": "lit-ext-only", "expected_sequence": 0, "material_ids": [], "external_refs": ext})
    assert ok.status_code == 201, ok.text
    empty = client.post(f"/api/v2/review-rounds/{rid}/literature-challenges", json={
        "command_id": "lit-none", "expected_sequence": 0, "material_ids": [], "external_refs": []})
    assert empty.status_code == 409  # 本 router 约定 BoundaryViolation → 409


def test_draft_prompts_are_anchored_on_question_and_claim():
    """#10: 覆盖梳理/gap/related-work 都要带研究问题(+claim),否则草稿顺着文献主题漂移。
    这里只证明接线;锚定效果须真模型复跑(feedback_prompt_change_live_verify)。"""
    store, universe, service, wid, mat, rid = _seed()
    seen: list[str] = []
    fake = type("F", (), {
        "complete": lambda self, s, u: seen.append(u) or '{"coverage_statement": "覆盖了对齐但缺推理评测", "search_query": "q", "counterexample_invitation": "c"}',
        "complete_json": lambda self, s, u, retries=2: {}})()
    app = FastAPI()
    app.include_router(create_dialogue_router(service, store, LibraryContext("lib"), None, client=fake), prefix="/api/v2")
    client = TestClient(app)
    for path in ("landscape-summary", "gap-draft", "related-work-draft"):
        assert client.post(f"/api/v2/workspaces/{wid}/dialogue/{path}", json={"material_ids": [mat]}).status_code == 200
    summary, gap, related = seen
    for prompt in seen:
        assert "Why does RLHF improve reasoning?" in prompt
    assert wid not in summary  # 以前把 workspace UUID 当成"问题方向"
    claim = "RLHF improves reasoning because it aligns preferences."
    assert claim in gap
    assert claim in summary
    assert claim not in related  # Q2: related-work 只锚问题,带 claim 会把文献按 claim 结构掰弯


class _Checker:
    """complete() 依次吐 texts;complete_json 记录 prompt 并回放 verdicts(或抛错)。"""
    def __init__(self, texts, verdicts=None, fail=False):
        self.texts, self.verdicts, self.fail = list(texts), verdicts, fail
        self.json_calls: list[str] = []
    def complete(self, system, user): return self.texts.pop(0)
    def complete_json(self, system, user, retries=2):
        self.json_calls.append(user)
        if self.fail:
            raise RuntimeError("checker down")
        return self.verdicts


def _desk(fake):
    store, universe, service, wid, mat, rid = _seed()
    app = FastAPI()
    app.include_router(create_dialogue_router(service, store, LibraryContext("lib"), None, client=fake), prefix="/api/v2")
    return TestClient(app), wid, mat, service, universe


def test_unselected_locator_flagged_without_checker_call():
    fake = _Checker(["RLHF 提升了推理 [arxiv:9999.99999]。"])
    client, wid, mat, *_ = _desk(fake)
    body = client.post(f"/api/v2/workspaces/{wid}/dialogue/landscape-summary", json={"material_ids": [mat]}).json()
    assert fake.json_calls == []
    assert body["citation_check_status"] == "ok"
    assert [(c["locator"], c["verdict"], c["scope"]) for c in body["citation_checks"]] == [("arxiv:9999.99999", "not_selected", None)]


def test_no_citations_no_checker_call():
    fake = _Checker(["没有任何引用的一段话。"])
    client, wid, mat, *_ = _desk(fake)
    body = client.post(f"/api/v2/workspaces/{wid}/dialogue/related-work-draft", json={"material_ids": [mat]}).json()
    assert fake.json_calls == []
    assert body["citation_checks"] == [] and body["citation_check_status"] == "ok"


def test_checker_scopes_abstract_excerpt_full():
    fake = _Checker(
        ["第一句引用摘要 [doi:10.1000/ext]。第二句引用长文 [arxiv:2401.00002]。第三句引用短文 [arxiv:2401.00001]。"],
        verdicts={"checks": [{"i": 1, "supported": False}, {"i": 2, "supported": False}, {"i": 3, "supported": True}]},
    )
    client, wid, mat, service, universe = _desk(fake)
    long_mat = service.add_material(universe, wid, "# long\n\n" + "x" * 7000, "arxiv:2401.00002", "parsed", "evidence", "m-long", 0).result_payload["material_id"]
    ext = [{"locator": "doi:10.1000/ext", "excerpt": "external abstract only.", "url": None}]
    body = client.post(f"/api/v2/workspaces/{wid}/dialogue/landscape-summary", json={"material_ids": [mat, long_mat], "external_refs": ext}).json()
    assert len(fake.json_calls) == 1
    # 核对者看到的文本比起草(1500)长,但封顶 6000
    assert "x" * 5000 in fake.json_calls[0] and "x" * 6001 not in fake.json_calls[0]
    got = {c["locator"]: (c["verdict"], c["scope"]) for c in body["citation_checks"]}
    assert got == {"doi:10.1000/ext": ("unsupported", "abstract"), "arxiv:2401.00002": ("unsupported", "excerpt"), "arxiv:2401.00001": ("supported", "full")}


def test_checker_failure_or_garbage_returns_draft_unavailable():
    for fake in (_Checker(["有引用 [arxiv:2401.00001]。"], fail=True), _Checker(["有引用 [arxiv:2401.00001]。"], verdicts={"nonsense": 1})):
        client, wid, mat, *_ = _desk(fake)
        resp = client.post(f"/api/v2/workspaces/{wid}/dialogue/related-work-draft", json={"material_ids": [mat]})
        assert resp.status_code == 200
        assert resp.json()["text"].startswith("有引用") and resp.json()["citation_check_status"] == "unavailable"


def test_gap_draft_checks_coverage_statement_and_material_lines_carry_scope():
    gap = json.dumps({"coverage_statement": "文献覆盖了评测方法,但缺推理应用 [arxiv:2401.00001]。", "search_query": "q", "counterexample_invitation": "c"})
    fake = _Checker([gap], verdicts={"checks": [{"i": 1, "supported": False}]})
    seen: list[str] = []
    orig = fake.complete
    fake.complete = lambda s, u: seen.append(u) or orig(s, u)
    client, wid, mat, *_ = _desk(fake)
    ext = [{"locator": "doi:10.1000/ext", "excerpt": "external abstract only.", "url": None}]
    body = client.post(f"/api/v2/workspaces/{wid}/dialogue/gap-draft", json={"material_ids": [mat], "external_refs": ext}).json()
    assert body["coverage_statement"].startswith("文献覆盖了") and body["citation_checks"][0]["verdict"] == "unsupported"
    assert "[doi:10.1000/ext] " in seen[0] and "范围:仅摘要" in seen[0] and "范围:全文" in seen[0]
