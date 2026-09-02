from fastapi.testclient import TestClient
from cui.api.app import create_native_test_app
from cui.research_universe.application import ChallengeDraft
from cui.research_universe.store.event_store import InMemoryNativeEventStore

class FakeGenerator:
    def generate(self, *, question, claim):
        return ChallengeDraft("causal gap", "the claim outruns the question evidence", "seek a counterexample", "fake-v1", "fake", ["question", "claim"], "moderate")

def _workspace(client, uid):
    response = client.post(f"/api/v2/universes/{uid}/workspaces", json={"command_id":"w", "expected_sequence":0, "question":"Does X cause Y?"})
    assert response.status_code == 201
    return response.json()["result"]["workspace_id"]

def test_public_slice1_routes_and_old_accidental_routes_are_404():
    store = InMemoryNativeEventStore(); uid = store.create_active_universe("default")
    client = TestClient(create_native_test_app(store, challenge_generator=FakeGenerator()))
    wid = _workspace(client, uid)
    note = client.post(f"/api/v2/workspaces/{wid}/notes", json={"command_id":"n", "expected_sequence":1, "text":"A useful observation."})
    assert note.status_code == 200
    assert client.post(f"/api/v2/universes/workspaces/{wid}/notes", json={"command_id":"old", "expected_sequence":2, "text":"no"}).status_code == 404
    assert client.get(f"/api/v2/workspaces/{wid}").status_code == 200
    assert client.get(f"/api/v2/universes/workspaces/{wid}").status_code == 404

def test_note_revisions_preserve_old_anchor_and_report_authoritative_workspace_sequence():
    store = InMemoryNativeEventStore(); uid = store.create_active_universe("default")
    client = TestClient(create_native_test_app(store, challenge_generator=FakeGenerator()))
    wid = _workspace(client, uid)
    first = client.post(f"/api/v2/workspaces/{wid}/notes", json={"command_id":"n1", "expected_sequence":1, "text":"A useful observation."})
    assert first.status_code == 200
    first_result = first.json()["result"]
    anchor = client.post(f"/api/v2/workspaces/{wid}/anchors", json={"command_id":"a", "expected_sequence":2, "note_id":first_result["note_id"], "note_revision_id":first_result["note_revision_id"], "start":0, "end":6, "selected_text":"A usef"})
    assert anchor.status_code == 200
    second = client.post(f"/api/v2/workspaces/{wid}/notes", json={"command_id":"n2", "expected_sequence":3, "text":"A revised observation."})
    assert second.status_code == 200
    second_result = second.json()["result"]
    assert second_result["note_id"] == first_result["note_id"]
    assert second_result["note_revision_id"] != first_result["note_revision_id"]
    assert second.json()["result"]["aggregate_sequences"] == {"workspace": 4}
    replay = client.post(f"/api/v2/workspaces/{wid}/notes", json={"command_id":"n2", "expected_sequence":3, "text":"A revised observation."})
    assert replay.status_code == 200 and replay.json()["result"] == second_result
    assert second.json()["fragment"]["sequence"] == 4
    workspace = client.get(f"/api/v2/workspaces/{wid}").json()
    assert workspace["note"] == {"id": second_result["note_revision_id"], "note_id": first_result["note_id"], "text": "A revised observation.", "sequence": 3}
    assert [r["id"] for r in workspace["note_revisions"]] == [first_result["note_revision_id"], second_result["note_revision_id"]]
    assert workspace["anchors"][0]["note_revision_id"] == first_result["note_revision_id"]
    stale = client.post(f"/api/v2/workspaces/{wid}/notes", json={"command_id":"stale", "expected_sequence":3, "text":"no"})
    assert stale.status_code == 409

def test_first_fact_round_trip_and_same_pending_identity():
    store = InMemoryNativeEventStore(); uid = store.create_active_universe("default")
    client = TestClient(create_native_test_app(store, challenge_generator=FakeGenerator()))
    wid = _workspace(client, uid)
    note = client.post(f"/api/v2/workspaces/{wid}/notes", json={"command_id":"n", "expected_sequence":1, "text":"A useful observation."}).json()
    client.post(f"/api/v2/workspaces/{wid}/anchors", json={"command_id":"a", "expected_sequence":2, "note_id":note["result"]["note_id"], "note_revision_id":note["result"]["note_revision_id"], "start":0,"end":6,"selected_text":"A usef"})
    claim = client.post(f"/api/v2/workspaces/{wid}/claims", json={"command_id":"c", "expected_sequence":0, "text":"X causes Y."}).json(); cid=claim["result"]["claim_id"]
    rnd = client.post(f"/api/v2/claims/{cid}/review-rounds", json={"command_id":"r", "expected_sequence":0}).json(); rid=rnd["result"]["review_round_id"]
    workspace = client.get(f"/api/v2/workspaces/{wid}").json(); home=client.get(f"/api/v2/universes/{uid}/home").json()
    assert rnd["fragment"]["challenges"][0]["id"] == workspace["pending_challenges"][0]["id"] == home["pending_facts"][0]["id"]
    assert home["pending_facts"][0]["review_round_id"] == rid

def test_generator_failure_is_atomic():
    class Broken:
        def generate(self, **kwargs): raise RuntimeError("down")
    store=InMemoryNativeEventStore(); uid=store.create_active_universe("default"); c=TestClient(create_native_test_app(store, challenge_generator=Broken()))
    wid=_workspace(c, uid)
    cid=c.post(f"/api/v2/workspaces/{wid}/claims",json={"command_id":"c","expected_sequence":0,"text":"C"}).json()["result"]["claim_id"]
    assert c.post(f"/api/v2/claims/{cid}/review-rounds",json={"command_id":"r","expected_sequence":0}).status_code == 502
    assert len(store.read_events(uid)) == 2
