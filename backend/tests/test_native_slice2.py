from fastapi.testclient import TestClient
from anneal.api.app import create_native_test_app
from anneal.research_universe.application import ChallengeDraft
from anneal.research_universe.store.event_store import InMemoryNativeEventStore

class NoModel:
    def generate(self, **kwargs): raise AssertionError("PARK must not call a model")

def workspace(c, uid, command="w"):
    return c.post(f"/api/v2/universes/{uid}/workspaces", json={"command_id":command,"expected_sequence":0,"question":"User question"}).json()["result"]["workspace_id"]

def test_park_firewall_immutable_release_and_forge_lineage():
    store=InMemoryNativeEventStore(); uid=store.create_active_universe("default"); c=TestClient(create_native_test_app(store, challenge_generator=NoModel()))
    raw="Unfinished private hunch"
    cap=c.post("/api/v2/park-captures",json={"command_id":"cap","expected_sequence":0,"original_text":raw})
    assert cap.status_code == 201; capture_id=cap.json()["result"]["capture_id"]
    assert raw not in str(c.get(f"/api/v2/universes/{uid}/home").json())
    listed=c.get("/api/v2/park-captures").json()
    assert raw not in str(listed) and "original_text" not in listed["captures"][0]
    assert c.get(f"/api/v2/park-captures/{capture_id}").json()["original_text"] == raw
    wid=workspace(c,uid)
    rel=c.post(f"/api/v2/park-captures/{capture_id}/release",json={"command_id":"rel","expected_sequence":0,"workspace_id":wid,"provisional_role":"material_lead"})
    assert rel.status_code == 200; release_id=rel.json()["result"]["release_id"]
    assert rel.json()["fragment"]["park_release_refs"] == [{"id":release_id,"capture_id":capture_id,"provisional_role":"material_lead"}]
    assert c.get(f"/api/v2/park-captures/{capture_id}").json()["original_text"] == raw
    claim=c.post(f"/api/v2/workspaces/{wid}/claims",json={"command_id":"claim","expected_sequence":0,"text":"My authored claim."}).json()["result"]["claim_id"]
    forged=c.post(f"/api/v2/workspaces/{wid}/claims/forge-provenance",json={"command_id":"forge","expected_sequence":0,"claim_id":claim,"capture_id":capture_id,"release_id":release_id})
    assert forged.status_code == 200
    assert c.get(f"/api/v2/park-captures/{capture_id}").json()["forged_into"][0]["claim_id"] == claim

def test_release_new_workspace_atomic_idempotent_and_cross_universe_is_not_addressable():
    store=InMemoryNativeEventStore(); uid=store.create_active_universe("default"); c=TestClient(create_native_test_app(store, challenge_generator=NoModel()))
    cap=c.post("/api/v2/park-captures",json={"command_id":"cap","expected_sequence":0,"original_text":"raw"}).json(); cid=cap["result"]["capture_id"]
    body={"command_id":"release","expected_sequence":0,"question":"A user question","provisional_role":"trigger_question"}
    first=c.post(f"/api/v2/park-captures/{cid}/release",json=body); replay=c.post(f"/api/v2/park-captures/{cid}/release",json=body)
    assert first.status_code == 200 and replay.status_code == 200 and first.json()["result"] == replay.json()["result"]
    wid=first.json()["result"]["workspace_id"]
    assert c.get(f"/api/v2/workspaces/{wid}").json()["question"]["text"] == "A user question"
    assert len(store.read_events(uid)) == 2
    assert c.post(f"/api/v2/park-captures/{cid}/release",json={**body,"command_id":"bad","workspace_id":wid}).status_code == 422
