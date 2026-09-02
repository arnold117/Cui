"""slice1 S1.2/S1.3 — gap candidate lifecycle + landscape contract tests."""
from fastapi.testclient import TestClient

from cui.api.app import create_native_test_app
from cui.research_universe.api.routes import LibraryContext
from cui.research_universe.application import ChallengeDraft, Slice1Service
from cui.research_universe.domain.events import validate_payload
from cui.research_universe.store.event_store import InMemoryNativeEventStore
from cui.tools.v4_importer import ACTIVE_WS_COMMAND, workspace_id_for


class _Gen:
    def generate(self, *, question, claim):
        return ChallengeDraft("x", "y", "z", "p", "m", ["review_round.question_snapshot", "review_round.claim_snapshot"], "low")

    def generate_additional(self, **_): raise AssertionError("unused")


def _seed():
    store = InMemoryNativeEventStore()
    universe = store.create_active_universe("lib")
    service = Slice1Service(store, "local", _Gen())
    wid = service.create_workspace(universe, "w1", 0, "Why does X matter?").result_payload["workspace_id"]
    app = create_native_test_app(store, LibraryContext("lib"), principal=None, challenge_generator=_Gen())
    return TestClient(app), wid


def _propose(client, wid, command_id="g1", expected_sequence=0, **overrides):
    body = {
        "command_id": command_id,
        "expected_sequence": expected_sequence,
        "coverage_statement": "现有文献覆盖了 X 的机制测量,但没有覆盖其在真实任务上的表现边界。",
        "search_query": "X real-task evaluation",
        "search_scope": "active",
        "matched_locators": ["arxiv:2401.00001"],
        "searched_at": "2026-09-02",
        "counterexample_invitation": "如果你知道任何在真实任务上测量过 X 的工作,请指出。",
    }
    body.update(overrides)
    return client.post(f"/api/v2/workspaces/{wid}/gap-candidates", json=body)


def test_gap_payload_catalogue_validates():
    ok = validate_payload("gap_candidate_proposed", 1, {
        "gap_candidate_id": "g", "workspace_id": "w", "coverage_statement": "覆盖声明至少要十个字长度起",
        "search_query": "q", "search_scope": "active", "matched_locators": [], "searched_at": None,
        "counterexample_invitation": "欢迎反例", "generator_kind": "user", "author": "user"})
    assert ok.coverage_statement
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        validate_payload("gap_candidate_proposed", 1, {"gap_candidate_id": "g", "workspace_id": "w", "coverage_statement": "短", "search_query": "q", "counterexample_invitation": "x"})


def test_propose_confirm_lifecycle_round_trip():
    client, wid = _seed()
    proposed = _propose(client, wid)
    assert proposed.status_code == 201, proposed.text
    gap_id = proposed.json()["result"]["gap_candidate_id"]
    assert [g["status"] for g in proposed.json()["fragment"]["gaps"]] == ["pending"]
    confirmed = client.post(f"/api/v2/gap-candidates/{gap_id}/confirm",
                            json={"command_id": "g1-confirm", "expected_sequence": 1, "user_reason": "人审通过"})
    assert confirmed.status_code in (200, 201), confirmed.text
    gaps = confirmed.json()["fragment"]["gaps"]
    gap = next(g for g in gaps if g["id"] == gap_id)
    assert gap["status"] == "confirmed" and gap["decision_reason"] == "人审通过"
    assert gap["search_record"]["query"] == "X real-task evaluation"
    assert gap["counterexample_invitation"]


def test_correct_updates_coverage_statement():
    client, wid = _seed()
    gap_id = _propose(client, wid).json()["result"]["gap_candidate_id"]
    fixed = client.post(f"/api/v2/gap-candidates/{gap_id}/correct",
                        json={"command_id": "g1-correct", "expected_sequence": 1,
                              "corrected_coverage_statement": "修订后的覆盖声明:边界表述更新为……至少十字", "user_reason": "边界写窄了"})
    assert fixed.status_code in (200, 201), fixed.text
    gap = next(g for g in fixed.json()["fragment"]["gaps"] if g["id"] == gap_id)
    assert gap["status"] == "corrected"
    assert gap["coverage_statement"].startswith("修订后的覆盖声明")


def test_decisions_are_terminal_and_single():
    client, wid = _seed()
    gap_id = _propose(client, wid).json()["result"]["gap_candidate_id"]
    rejected = client.post(f"/api/v2/gap-candidates/{gap_id}/reject",
                           json={"command_id": "g1-reject", "expected_sequence": 1, "user_reason": "反例成立"})
    assert rejected.status_code in (200, 201)
    again = client.post(f"/api/v2/gap-candidates/{gap_id}/confirm",
                        json={"command_id": "g1-confirm-again", "expected_sequence": 1, "user_reason": "再想想"})
    assert again.status_code == 409  # old decisions are never reopened


def test_withdraw_and_landscape_readback():
    client, wid = _seed()
    gap_id = _propose(client, wid, command_id="gw").json()["result"]["gap_candidate_id"]
    landscape = client.get(f"/api/v2/workspaces/{wid}/landscape").json()
    assert landscape["workspace_id"] == wid
    assert [g["status"] for g in landscape["gaps"]] == ["pending"]
    withdrawn = client.post(f"/api/v2/gap-candidates/{gap_id}/withdraw",
                            json={"command_id": "gw-withdraw", "expected_sequence": 1, "user_reason": "撤回重写"})
    assert withdrawn.status_code in (200, 201)
    assert next(g for g in withdrawn.json()["fragment"]["gaps"] if g["id"] == gap_id)["status"] == "withdrawn"


def test_gap_unknown_workspace_404_and_validation_errors():
    client, wid = _seed()
    assert client.post("/api/v2/workspaces/nope/gap-candidates",
                       json={"command_id": "x", "expected_sequence": 0, "coverage_statement": "覆盖声明足够长十个字了吧", "search_query": "q", "counterexample_invitation": "邀请"}).status_code == 404
    assert _propose(client, wid, coverage_statement="太短").status_code == 422
