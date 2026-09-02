"""slice1 second cut — literature challenge + dialogue transient endpoints."""
import json

import pytest
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
        json.dumps({"coverage_statement": "文献覆盖了评测方法,但没有覆盖推理链上的真实应用缺口。", "search_query": "RLHF reasoning evaluation", "counterexample_invitation": "如有推理任务上的 RLHF 数据请指正。"}),
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
