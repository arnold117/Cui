"""Slice 5 workspace crystallization / direction impact tests (in-memory)."""
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from cui.api.app import create_native_test_app
from cui.research_universe.application import ChallengeDraft, direction_projection, workspace_projection
from cui.research_universe.domain.events import validate_payload
from cui.research_universe.store.event_store import InMemoryNativeEventStore


class FakeGenerator:
    def generate(self, *, question, claim):
        return ChallengeDraft("causal gap", "why it matters", "seek a counterexample", "fake-v1", "fake", ["question", "claim"], "moderate")


def setup():
    store = InMemoryNativeEventStore(); uid = store.create_active_universe("default")
    client = TestClient(create_native_test_app(store, challenge_generator=FakeGenerator()))
    return store, uid, client


def _workspace(client, uid, command_id="w", question="Does X cause Y?"):
    r = client.post(f"/api/v2/universes/{uid}/workspaces", json={"command_id": command_id, "expected_sequence": 0, "question": question})
    assert r.status_code == 201, r.text
    return r.json()["result"]["workspace_id"]


def _tracer(client, uid, wcid="w", ccid="c", rcid="r"):
    wid = _workspace(client, uid, wcid)
    cid = client.post(f"/api/v2/workspaces/{wid}/claims", json={"command_id": ccid, "expected_sequence": 0, "text": "X causes Y."}).json()["result"]["claim_id"]
    rid = client.post(f"/api/v2/claims/{cid}/review-rounds", json={"command_id": rcid, "expected_sequence": 0}).json()["result"]["review_round_id"]
    return wid, cid, rid


def _seq(client, wid):
    return client.get(f"/api/v2/workspaces/{wid}").json()["sequence"]


def _direction(client, uid, command_id="d", proposition="I pursue a long-term thesis."):
    r = client.post(f"/api/v2/universes/{uid}/directions", json={"command_id": command_id, "expected_sequence": 0, "proposition": proposition})
    assert r.status_code == 201, r.text
    return r.json()["result"]["direction_id"]


def _conclude(client, wid, command_id="conc", conclusion_type="tentative_answer", conclusion_text="The answer is X.", basis_refs=None, revival_condition=None):
    body = {"command_id": command_id, "expected_sequence": _seq(client, wid), "conclusion_type": conclusion_type, "conclusion_text": conclusion_text}
    if basis_refs is not None: body["basis_refs"] = basis_refs
    if revival_condition is not None: body["revival_condition"] = revival_condition
    return client.post(f"/api/v2/workspaces/{wid}/conclusions", json=body)


# --- payload catalogue -------------------------------------------------------

def test_slice5_payload_catalogue_validates_and_rejects_malformed():
    assert validate_payload("workspace_paused", 1, {"workspace_id": "w"}).user_reason is None
    assert validate_payload("workspace_reopened", 1, {"workspace_id": "w", "user_reason": "back"}).user_reason == "back"
    with pytest.raises(ValidationError): validate_payload("workspace_paused", 1, {"workspace_id": "w", "bogus": 1})
    p = validate_payload("workspace_concluded", 1, {"workspace_id": "w", "conclusion_id": "c", "conclusion_type": "tentative_answer", "conclusion_text": "done", "basis_refs": ["b"], "revival_condition": None})
    assert p.new_user_position == "concluded" and p.basis_refs == ["b"]
    with pytest.raises(ValidationError): validate_payload("workspace_concluded", 1, {"workspace_id": "w", "conclusion_id": "c", "conclusion_type": "tentative_answer", "conclusion_text": ""})
    with pytest.raises(ValidationError): validate_payload("workspace_concluded", 1, {"workspace_id": "w", "conclusion_id": "c", "conclusion_type": "bogus", "conclusion_text": "x"})
    # deferred requires revival_condition
    assert validate_payload("workspace_concluded", 1, {"workspace_id": "w", "conclusion_id": "c", "conclusion_type": "deferred", "conclusion_text": "later", "revival_condition": "when data arrives"}).revival_condition == "when data arrives"
    with pytest.raises(ValidationError): validate_payload("workspace_concluded", 1, {"workspace_id": "w", "conclusion_id": "c", "conclusion_type": "deferred", "conclusion_text": "later"})
    # non-deferred must not carry revival_condition
    with pytest.raises(ValidationError): validate_payload("workspace_concluded", 1, {"workspace_id": "w", "conclusion_id": "c", "conclusion_type": "tentative_answer", "conclusion_text": "x", "revival_condition": "nope"})
    bp = validate_payload("workspace_branched", 1, {"workspace_id": "w", "successor_workspace_id": "s", "user_reason": "split"})
    assert bp.new_user_position == "branched"
    with pytest.raises(ValidationError): validate_payload("workspace_branched", 1, {"workspace_id": "w", "successor_workspace_id": "s", "user_reason": ""})
    ap = validate_payload("workspace_absorbed", 1, {"workspace_id": "w", "target_workspace_id": "t", "user_reason": "merge"})
    assert ap.new_user_position == "absorbed"
    dc = validate_payload("direction_created", 1, {"direction_id": "d", "proposition_version_id": "v", "proposition_text": "thesis"})
    assert dc.declared_status == "active" and dc.author == "user"
    with pytest.raises(ValidationError): validate_payload("direction_created", 1, {"direction_id": "d", "proposition_version_id": "v", "proposition_text": ""})
    assert validate_payload("direction_status_declared", 1, {"direction_id": "d", "status": "on_hold", "user_reason": "pausing"}).status == "on_hold"
    with pytest.raises(ValidationError): validate_payload("direction_status_declared", 1, {"direction_id": "d", "status": "bogus", "user_reason": "x"})
    with pytest.raises(ValidationError): validate_payload("direction_status_declared", 1, {"direction_id": "d", "status": "active", "user_reason": ""})
    rp = validate_payload("direction_proposition_rephrased", 1, {"direction_id": "d", "prior_proposition_version_id": "pv", "prior_proposition_text": "old", "new_proposition_version_id": "nv", "new_proposition_text": "new", "change_type": "clarify", "user_reason": "clearer", "source_conclusion_ref": "c"})
    assert rp.change_type == "clarify" and rp.source_conclusion_ref == "c"
    # unnamed requires null proposition and vice versa
    un = validate_payload("direction_proposition_rephrased", 1, {"direction_id": "d", "prior_proposition_version_id": "pv", "prior_proposition_text": "old", "new_proposition_version_id": "nv", "new_proposition_text": None, "change_type": "unnamed", "user_reason": "don't know yet"})
    assert un.new_proposition_text is None
    with pytest.raises(ValidationError): validate_payload("direction_proposition_rephrased", 1, {"direction_id": "d", "prior_proposition_version_id": "pv", "prior_proposition_text": "old", "new_proposition_version_id": "nv", "new_proposition_text": "filled", "change_type": "unnamed", "user_reason": "x"})
    with pytest.raises(ValidationError): validate_payload("direction_proposition_rephrased", 1, {"direction_id": "d", "prior_proposition_version_id": "pv", "prior_proposition_text": "old", "new_proposition_version_id": "nv", "new_proposition_text": "", "change_type": "clarify", "user_reason": "x"})
    with pytest.raises(ValidationError): validate_payload("direction_proposition_rephrased", 1, {"direction_id": "d", "prior_proposition_version_id": "pv", "prior_proposition_text": "old", "new_proposition_version_id": "nv", "new_proposition_text": None, "change_type": "turning", "user_reason": "x"})
    assert validate_payload("workspace_direction_attached", 1, {"direction_link_id": "l", "workspace_id": "w", "direction_id": "d"}).user_reason is None
    assert validate_payload("workspace_direction_detached", 1, {"direction_link_id": "l", "workspace_id": "w", "direction_id": "d"}).direction_id == "d"
    cr = validate_payload("workspace_crystallization_attached", 1, {"crystallization_id": "x", "direction_id": "d", "workspace_id": "w", "conclusion_id": "c", "conclusion_text": "done", "conclusion_type": "boundary"})
    assert cr.conclusion_type == "boundary"


# --- position state machine --------------------------------------------------

def test_position_state_machine_valid_and_invalid_transitions():
    store, uid, client = setup()
    wid = _workspace(client, uid)
    # exploring -> paused
    assert client.post(f"/api/v2/workspaces/{wid}/pause", json={"command_id": "p1", "expected_sequence": _seq(client, wid)}).status_code == 200
    assert client.get(f"/api/v2/workspaces/{wid}").json()["user_position"] == "paused"
    # paused -> reopen
    assert client.post(f"/api/v2/workspaces/{wid}/reopen", json={"command_id": "r1", "expected_sequence": _seq(client, wid)}).status_code == 200
    assert client.get(f"/api/v2/workspaces/{wid}").json()["user_position"] == "exploring"
    # exploring -> conclude
    assert _conclude(client, wid, command_id="c1").status_code == 200
    assert client.get(f"/api/v2/workspaces/{wid}").json()["user_position"] == "concluded"
    # concluded -> reopen
    assert client.post(f"/api/v2/workspaces/{wid}/reopen", json={"command_id": "r2", "expected_sequence": _seq(client, wid)}).status_code == 200
    assert client.get(f"/api/v2/workspaces/{wid}").json()["user_position"] == "exploring"
    # conclude while paused is rejected
    client.post(f"/api/v2/workspaces/{wid}/pause", json={"command_id": "p2", "expected_sequence": _seq(client, wid)})
    assert _conclude(client, wid, command_id="c2").status_code == 409
    # branch a paused workspace is rejected
    assert client.post(f"/api/v2/workspaces/{wid}/branch", json={"command_id": "b1", "expected_sequence": _seq(client, wid), "new_question": "Next?", "user_reason": "split"}).status_code == 409
    # second conclude after a fresh conclude is rejected
    client.post(f"/api/v2/workspaces/{wid}/reopen", json={"command_id": "r3", "expected_sequence": _seq(client, wid)})
    _conclude(client, wid, command_id="c3")
    assert _conclude(client, wid, command_id="c4").status_code == 409
    # reopen an exploring workspace is rejected
    client.post(f"/api/v2/workspaces/{wid}/reopen", json={"command_id": "r4", "expected_sequence": _seq(client, wid)})
    assert client.post(f"/api/v2/workspaces/{wid}/reopen", json={"command_id": "r5", "expected_sequence": _seq(client, wid)}).status_code == 409
    # pause an already paused workspace is rejected
    client.post(f"/api/v2/workspaces/{wid}/pause", json={"command_id": "p3", "expected_sequence": _seq(client, wid)})
    assert client.post(f"/api/v2/workspaces/{wid}/pause", json={"command_id": "p4", "expected_sequence": _seq(client, wid)}).status_code == 409


def test_branch_and_absorb_from_concluded_are_valid():
    store, uid, client = setup()
    wid = _workspace(client, uid)
    other = _workspace(client, uid, command_id="other", question="Another question?")
    _conclude(client, wid, command_id="c1")
    r = client.post(f"/api/v2/workspaces/{wid}/branch", json={"command_id": "b1", "expected_sequence": _seq(client, wid), "new_question": "Successor?", "user_reason": "split after conclusion"})
    assert r.status_code == 200
    assert client.get(f"/api/v2/workspaces/{wid}").json()["user_position"] == "branched"
    # a second workspace concluded then absorbed
    wid2 = _workspace(client, uid, command_id="w2")
    _conclude(client, wid2, command_id="c2")
    assert client.post(f"/api/v2/workspaces/{wid2}/absorb", json={"command_id": "a1", "expected_sequence": _seq(client, wid2), "target_workspace_id": other, "user_reason": "merge"}).status_code == 200
    assert client.get(f"/api/v2/workspaces/{wid2}").json()["user_position"] == "absorbed"


def test_branch_creates_successor_and_records_source_atomically():
    store, uid, client = setup()
    wid = _workspace(client, uid)
    before = len(store.read_events(uid))
    r = client.post(f"/api/v2/workspaces/{wid}/branch", json={"command_id": "b1", "expected_sequence": _seq(client, wid), "new_question": "New branch question", "user_reason": "split"})
    assert r.status_code == 200
    successor_id = r.json()["result"]["successor_workspace_id"]
    events = store.read_events(uid)
    assert len(events) == before + 2
    created = [e for e in events if e.event_type == "workspace_created" and e.validated_payload().workspace_id == successor_id]
    branched = [e for e in events if e.event_type == "workspace_branched"]
    assert len(created) == 1 and len(branched) == 1
    # both in the SAME commit
    assert created[0].commit_position == branched[0].commit_position
    assert created[0].validated_payload().initial_question_text == "New branch question"
    assert branched[0].validated_payload().successor_workspace_id == successor_id
    src = client.get(f"/api/v2/workspaces/{wid}").json()
    assert src["user_position"] == "branched" and src["successor_workspace_id"] == successor_id
    succ = client.get(f"/api/v2/workspaces/{successor_id}").json()
    assert succ["user_position"] == "exploring" and succ["question"]["text"] == "New branch question"


def test_absorb_validates_target_and_records_source():
    store, uid, client = setup()
    wid = _workspace(client, uid)
    other = _workspace(client, uid, command_id="other", question="Target?")
    # same workspace
    assert client.post(f"/api/v2/workspaces/{wid}/absorb", json={"command_id": "a1", "expected_sequence": _seq(client, wid), "target_workspace_id": wid, "user_reason": "self"}).status_code == 409
    # nonexistent target
    assert client.post(f"/api/v2/workspaces/{wid}/absorb", json={"command_id": "a2", "expected_sequence": _seq(client, wid), "target_workspace_id": "nope", "user_reason": "merge"}).status_code == 404
    r = client.post(f"/api/v2/workspaces/{wid}/absorb", json={"command_id": "a3", "expected_sequence": _seq(client, wid), "target_workspace_id": other, "user_reason": "merge into the main thread"})
    assert r.status_code == 200
    ws = client.get(f"/api/v2/workspaces/{wid}").json()
    assert ws["user_position"] == "absorbed" and ws["absorb_target_workspace_id"] == other


# --- pending facts never block lifecycle --------------------------------------

def test_conclude_with_pending_challenge_succeeds():
    store, uid, client = setup()
    wid, cid, rid = _tracer(client, uid)
    ws = client.get(f"/api/v2/workspaces/{wid}").json()
    assert len(ws["pending_challenges"]) == 1
    r = _conclude(client, wid, command_id="c1", conclusion_type="boundary", conclusion_text="X needs a narrower scope.")
    assert r.status_code == 200
    concluded = client.get(f"/api/v2/workspaces/{wid}").json()
    assert concluded["user_position"] == "concluded"
    # contextual facts remain visible on a concluded workspace
    assert len(concluded["pending_challenges"]) == 1
    assert concluded["pending_challenges"][0]["id"] == ws["pending_challenges"][0]["id"]


# --- direction lifecycle -----------------------------------------------------

def test_direction_create_attach_crystallize_rephrase_status():
    store, uid, client = setup()
    wid = _workspace(client, uid)
    did = _direction(client, uid)
    # attach direction to workspace
    link = client.post(f"/api/v2/workspaces/{wid}/direction-links", json={"command_id": "link", "expected_sequence": 0, "direction_id": did})
    assert link.status_code == 201
    link_id = link.json()["result"]["direction_link_id"]
    ws = client.get(f"/api/v2/workspaces/{wid}").json()
    assert ws["direction_links"][0]["direction_id"] == did and ws["direction_links"][0]["direction_proposition"] == "I pursue a long-term thesis."
    # conclude then crystallize
    _conclude(client, wid, command_id="conc", conclusion_type="tentative_answer", conclusion_text="The answer is X.")
    conclusion_id = client.get(f"/api/v2/workspaces/{wid}").json()["conclusion"]["id"]
    cr = client.post(f"/api/v2/directions/{did}/crystallizations", json={"command_id": "x", "expected_sequence": 0, "workspace_id": wid, "conclusion_id": conclusion_id})
    assert cr.status_code == 201
    xid = cr.json()["result"]["crystallization_id"]
    # rephrase with source_conclusion_ref preserved
    rp = client.post(f"/api/v2/directions/{did}/rephrasings", json={"command_id": "rp", "expected_sequence": 1, "new_proposition": "Narrower thesis.", "change_type": "narrow_or_widen", "user_reason": "after the crystallization", "source_conclusion_ref": conclusion_id})
    assert rp.status_code == 200
    frag = rp.json()["fragment"]
    assert frag["proposition"]["text"] == "Narrower thesis."
    assert len(frag["rephrase_history"]) == 1
    assert frag["rephrase_history"][0]["prior_proposition_text"] == "I pursue a long-term thesis."
    assert frag["rephrase_history"][0]["new_proposition_text"] == "Narrower thesis."
    assert frag["rephrase_history"][0]["source_conclusion_ref"] == conclusion_id
    # unnamed rephrase explicitly clears the proposition
    rp2 = client.post(f"/api/v2/directions/{did}/rephrasings", json={"command_id": "rp2", "expected_sequence": 2, "new_proposition": None, "change_type": "unnamed", "user_reason": "old proposition insufficient"})
    assert rp2.status_code == 200
    frag2 = rp2.json()["fragment"]
    assert frag2["proposition"]["text"] is None
    assert len(frag2["rephrase_history"]) == 2
    assert frag2["rephrase_history"][1]["change_type"] == "unnamed"
    # status declared
    st = client.post(f"/api/v2/directions/{did}/status-declarations", json={"command_id": "st", "expected_sequence": 3, "status": "on_hold", "user_reason": "parking for now"})
    assert st.status_code == 200
    assert st.json()["fragment"]["status"] == "on_hold"
    # crystallizations and attached workspaces readable on direction projection
    dp = client.get(f"/api/v2/directions/{did}").json()
    assert dp["crystallizations"][0]["crystallization_id"] == xid
    assert dp["crystallizations"][0]["conclusion_text"] == "The answer is X."
    assert dp["attached_workspaces"][0]["workspace_id"] == wid
    assert dp["attached_workspaces"][0]["position"] == "concluded"
    assert dp["attached_workspaces"][0]["pending_fact_count"] == 0


def test_direction_attachment_requires_extant_direction_and_crystallization_requires_conclusion():
    store, uid, client = setup()
    wid = _workspace(client, uid)
    assert client.post(f"/api/v2/workspaces/{wid}/direction-links", json={"command_id": "link", "expected_sequence": 0, "direction_id": "nope"}).status_code == 404
    did = _direction(client, uid)
    assert client.post(f"/api/v2/workspaces/{wid}/direction-links", json={"command_id": "link2", "expected_sequence": 0, "direction_id": did}).status_code == 201
    # crystallization before any conclusion is a boundary violation
    assert client.post(f"/api/v2/directions/{did}/crystallizations", json={"command_id": "x", "expected_sequence": 0, "workspace_id": wid, "conclusion_id": "ghost"}).status_code == 409
    _conclude(client, wid, command_id="conc", conclusion_type="boundary", conclusion_text="bounded")
    conclusion_id = client.get(f"/api/v2/workspaces/{wid}").json()["conclusion"]["id"]
    # wrong conclusion id is rejected
    assert client.post(f"/api/v2/directions/{did}/crystallizations", json={"command_id": "x2", "expected_sequence": 0, "workspace_id": wid, "conclusion_id": "ghost"}).status_code == 409
    # crystallizing never changes the direction proposition
    assert client.post(f"/api/v2/directions/{did}/crystallizations", json={"command_id": "x3", "expected_sequence": 0, "workspace_id": wid, "conclusion_id": conclusion_id}).status_code == 201
    assert client.get(f"/api/v2/directions/{did}").json()["proposition"]["text"] == "I pursue a long-term thesis."


def test_detach_direction_link_removes_from_projections():
    store, uid, client = setup()
    wid = _workspace(client, uid)
    did = _direction(client, uid)
    link = client.post(f"/api/v2/workspaces/{wid}/direction-links", json={"command_id": "link", "expected_sequence": 0, "direction_id": did}).json()["result"]["direction_link_id"]
    assert len(client.get(f"/api/v2/workspaces/{wid}").json()["direction_links"]) == 1
    det = client.post(f"/api/v2/workspace-direction-links/{link}/detach", json={"command_id": "det", "expected_sequence": 1, "user_reason": "no longer fits"})
    assert det.status_code == 200
    assert client.get(f"/api/v2/workspaces/{wid}").json()["direction_links"] == []
    assert client.get(f"/api/v2/directions/{did}").json()["attached_workspaces"] == []
    # double detach is a boundary violation
    assert client.post(f"/api/v2/workspace-direction-links/{link}/detach", json={"command_id": "det2", "expected_sequence": 2, "user_reason": "again"}).status_code == 409
    assert client.post(f"/api/v2/workspace-direction-links/nope/detach", json={"command_id": "det3", "expected_sequence": 0, "user_reason": "x"}).status_code == 404


def test_rephrase_old_propositions_never_overwritten():
    store, uid, client = setup()
    did = _direction(client, uid)
    client.post(f"/api/v2/directions/{did}/rephrasings", json={"command_id": "rp1", "expected_sequence": 1, "new_proposition": "Second.", "change_type": "clarify", "user_reason": "clearer"})
    client.post(f"/api/v2/directions/{did}/rephrasings", json={"command_id": "rp2", "expected_sequence": 2, "new_proposition": "Third.", "change_type": "turning", "user_reason": "pivot"})
    dp = client.get(f"/api/v2/directions/{did}").json()
    assert [h["prior_proposition_text"] for h in dp["rephrase_history"]] == ["I pursue a long-term thesis.", "Second."]
    assert [h["new_proposition_text"] for h in dp["rephrase_history"]] == ["Second.", "Third."]
    assert [h["change_type"] for h in dp["rephrase_history"]] == ["clarify", "turning"]
    # the current proposition is the latest, not an overwrite
    assert dp["proposition"]["text"] == "Third."
    # no event was mutated: every rephrase is an immutable append
    assert len([e for e in store.read_events(uid) if e.event_type == "direction_proposition_rephrased"]) == 2


# --- projections -------------------------------------------------------------

def test_workspace_and_direction_projections_and_home_readback():
    store, uid, client = setup()
    wid = _workspace(client, uid)
    did = _direction(client, uid)
    client.post(f"/api/v2/workspaces/{wid}/direction-links", json={"command_id": "link", "expected_sequence": 0, "direction_id": did})
    _conclude(client, wid, command_id="conc", conclusion_type="key_unknown", conclusion_text="We do not know why.", basis_refs=["ref-a"])
    conclusion_id = client.get(f"/api/v2/workspaces/{wid}").json()["conclusion"]["id"]
    client.post(f"/api/v2/directions/{did}/crystallizations", json={"command_id": "x", "expected_sequence": 0, "workspace_id": wid, "conclusion_id": conclusion_id})
    ws = client.get(f"/api/v2/workspaces/{wid}").json()
    assert ws["user_position"] == "concluded"
    assert ws["conclusion"]["id"] == conclusion_id and ws["conclusion"]["type"] == "key_unknown"
    assert ws["conclusion"]["text"] == "We do not know why." and ws["conclusion"]["basis_refs"] == ["ref-a"]
    assert ws["direction_links"][0]["status"] == "active"
    dp = direction_projection(store, uid, did)
    assert dp["proposition"]["text"] == "I pursue a long-term thesis." and dp["status"] == "active"
    assert dp["crystallizations"][0]["conclusion_id"] == conclusion_id
    home = client.get(f"/api/v2/universes/{uid}/home").json()
    assert len(home["directions"]) == 1
    assert home["directions"][0]["id"] == did
    assert home["directions"][0]["proposition"] == "I pursue a long-term thesis."
    assert home["directions"][0]["crystallizations_count"] == 1
    assert home["directions"][0]["attached_workspaces_count"] == 1
    assert home["directions"][0]["crystallizations"][0]["conclusion_text"] == "We do not know why."
    # pending facts still readable alongside directions
    store2, uid2, client2 = setup()
    wid2, cid2, rid2 = _tracer(client2, uid2)
    home2 = client2.get(f"/api/v2/universes/{uid2}/home").json()
    assert len(home2["pending_facts"]) == 1
    assert home2["directions"] == []


# --- API integration / 409 / 404 ---------------------------------------------

def test_api_happy_paths_and_missing_targets():
    store, uid, client = setup()
    wid = _workspace(client, uid)
    # unknown workspace lifecycle commands are 404
    assert client.post("/api/v2/workspaces/nope/pause", json={"command_id": "p", "expected_sequence": 0}).status_code == 404
    assert client.post("/api/v2/workspaces/nope/branch", json={"command_id": "b", "expected_sequence": 0, "new_question": "Q", "user_reason": "r"}).status_code == 404
    assert client.post("/api/v2/workspaces/nope/conclusions", json={"command_id": "c", "expected_sequence": 0, "conclusion_type": "boundary", "conclusion_text": "x"}).status_code == 404
    assert client.get("/api/v2/directions/nope").status_code == 404
    assert client.post("/api/v2/directions/nope/status-declarations", json={"command_id": "s", "expected_sequence": 0, "status": "active", "user_reason": "r"}).status_code == 404
    assert client.post("/api/v2/directions/nope/rephrasings", json={"command_id": "r", "expected_sequence": 0, "new_proposition": "X", "change_type": "clarify", "user_reason": "r"}).status_code == 404
    assert client.post("/api/v2/directions/nope/crystallizations", json={"command_id": "x", "expected_sequence": 0, "workspace_id": wid, "conclusion_id": "c"}).status_code == 404
    # stale expected_sequence is 409
    did = _direction(client, uid)
    assert client.post(f"/api/v2/directions/{did}/status-declarations", json={"command_id": "s", "expected_sequence": 0, "status": "active", "user_reason": "r"}).status_code == 409


def test_no_auto_anything():
    store, uid, client = setup()
    wid = _tracer(client, uid)[0]
    _conclude(client, wid, command_id="c1", conclusion_type="boundary", conclusion_text="bound")
    types = [e.event_type for e in store.read_events(uid)]
    # concluding never creates/attaches/crystallizes/rephrases a direction
    assert "direction_created" not in types
    assert "workspace_direction_attached" not in types
    assert "workspace_crystallization_attached" not in types
    assert "direction_proposition_rephrased" not in types
    # direction commands are only ever explicit user commands
    did = _direction(client, uid)
    types2 = [e.event_type for e in store.read_events(uid)]
    assert "direction_created" in types2
    assert "workspace_direction_attached" not in types2
    assert "workspace_crystallization_attached" not in types2
    assert "direction_proposition_rephrased" not in types2


def test_reopen_keeps_conclusion_as_history():
    store, uid, client = setup()
    wid = _workspace(client, uid)
    _conclude(client, wid, command_id="c1", conclusion_type="tentative_answer", conclusion_text="A first answer.")
    assert client.post(f"/api/v2/workspaces/{wid}/reopen", json={"command_id": "r1", "expected_sequence": _seq(client, wid)}).status_code == 200
    ws = client.get(f"/api/v2/workspaces/{wid}").json()
    assert ws["user_position"] == "exploring"
    assert ws["conclusion"]["text"] == "A first answer."  # recorded history stays
