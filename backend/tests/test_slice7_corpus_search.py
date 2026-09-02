"""Slice1 S1.1 — corpus search endpoint contract tests (in-memory)."""
from fastapi.testclient import TestClient

from cui.api.app import create_native_test_app
from cui.research_universe.api.routes import LibraryContext
from cui.research_universe.application import ChallengeDraft, Slice1Service
from cui.research_universe.store.event_store import InMemoryNativeEventStore
from cui.tools.v4_importer import ACTIVE_WS_COMMAND, LEGACY_WS_COMMAND, workspace_id_for


class _Gen:
    def generate(self, *, question, claim):
        return ChallengeDraft("x", "y", "z", "p", "m", ["review_round.question_snapshot", "review_round.claim_snapshot"], "low")

    def generate_additional(self, **_): raise AssertionError("unused")


def _seed():
    store = InMemoryNativeEventStore()
    universe = store.create_active_universe("lib")
    service = Slice1Service(store, "local", _Gen())
    ws_active = workspace_id_for(ACTIVE_WS_COMMAND)
    ws_legacy = workspace_id_for(LEGACY_WS_COMMAND)
    service.create_workspace(universe, ACTIVE_WS_COMMAND, 0, "corpus active q")
    service.create_workspace(universe, LEGACY_WS_COMMAND, 0, "corpus legacy q")
    rows = [
        # (command suffix, group ws, locator, excerpt)
        ("a1", ws_active, "arxiv:2401.00001", "# Disengagement in moral psychology\n\npower and time model of moral disengagement\n"),
        ("a2", ws_active, "arxiv:2401.00002", "# Daily caffeine and recall\n\ncaffeine intake improves delayed recall in adults\n"),
        ("a3", ws_active, "arxiv:2301.00003", "# Power dynamics in small teams\n\npower asymmetries shape team conversation time\n"),
        ("a4", ws_active, "arxiv:2401.00004", "# 咖啡因与记忆\n\n咖啡因摄入改善成年人延迟回忆表现\n"),
        ("l1", ws_legacy, "doi:10.1007/x.00001", "# CHO cell culture\n\nbioprocess flux analysis of CHO cells\n"),
    ]
    for suffix, ws, locator, excerpt in rows:
        service.add_material(universe, ws, excerpt, locator, "parsed", "evidence", f"v4-import:{suffix}", 0)
    app = create_native_test_app(store, LibraryContext("lib"), principal=None, challenge_generator=_Gen())
    return TestClient(app), ws_active, ws_legacy


def _search(client, **params):
    return client.get("/api/v2/corpus/search", params=params)


def test_search_returns_ranked_results_active_default():
    client, *_ = _seed()
    resp = _search(client, q="disengagement moral")
    assert resp.status_code == 200
    body = resp.json()
    assert body["group"] == "active" and body["total"] == 4
    locators = [h["source_locator"] for h in body["results"]]
    assert locators[0] == "arxiv:2401.00001"  # rare term winner ranks first
    assert set(locators) <= {"arxiv:2401.00001", "arxiv:2401.00002", "arxiv:2301.00003", "arxiv:2401.00004"}


def test_search_active_excludes_legacy_workspace():
    client, *_ = _seed()
    resp = _search(client, q="CHO bioprocess")
    assert resp.status_code == 200
    assert resp.json()["results"] == []  # legacy corpus excluded by default


def test_search_legacy_group_includes_legacy():
    client, *_ = _seed()
    resp = _search(client, q="CHO bioprocess", group="legacy")
    assert resp.status_code == 200
    locators = [h["source_locator"] for h in resp.json()["results"]]
    assert "doi:10.1007/x.00001" in locators


def test_cjk_query_falls_back_to_raw_phrase():
    client, *_ = _seed()
    resp = _search(client, q="咖啡因摄入")
    assert resp.status_code == 200
    body = resp.json()
    # no CJK tokens survive extract_core_terms; fallback matches the Chinese excerpt
    assert body["results"], body


def test_empty_query_is_rejected():
    client, *_ = _seed()
    assert _search(client).status_code == 422
    assert _search(client, q="   ").status_code == 422


def test_search_is_deterministic():
    client, *_ = _seed()
    first = _search(client, q="recall caffeine").json()
    second = _search(client, q="recall caffeine").json()
    assert first["results"] == second["results"]


def test_results_carry_metadata_and_snippet():
    client, *_ = _seed()
    hit = _search(client, q="recall caffeine").json()["results"][0]
    assert hit["material_id"] and hit["title"].startswith("#") is False
    assert hit["source_locator"].startswith("arxiv:")
    assert hit["matched_terms"] >= 1
    assert len(hit["snippet"]) <= 300
