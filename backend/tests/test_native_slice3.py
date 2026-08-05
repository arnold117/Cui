"""Slice 3 review lifecycle / human verdict tests (in-memory domain/service/API)."""
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from anneal.api.app import create_native_test_app
from anneal.research_universe.application import ChallengeDraft
from anneal.research_universe.domain.events import validate_payload
from anneal.research_universe.store.event_store import InMemoryNativeEventStore


class FakeGenerator:
    def generate(self, *, question, claim):
        return ChallengeDraft("causal gap", "the claim outruns the question evidence", "seek a counterexample", "fake-v1", "fake", ["question", "claim"], "moderate")


def setup():
    store = InMemoryNativeEventStore(); uid = store.create_active_universe("default")
    client = TestClient(create_native_test_app(store, challenge_generator=FakeGenerator()))
    wid = client.post(f"/api/v2/universes/{uid}/workspaces", json={"command_id":"w", "expected_sequence":0, "question":"Does X cause Y?"}).json()["result"]["workspace_id"]
    cid = client.post(f"/api/v2/workspaces/{wid}/claims", json={"command_id":"c", "expected_sequence":0, "text":"X causes Y."}).json()["result"]["claim_id"]
    rnd = client.post(f"/api/v2/claims/{cid}/review-rounds", json={"command_id":"r", "expected_sequence":0}).json()
    rid = rnd["result"]["review_round_id"]; challenge_id = rnd["result"]["challenge_id"]
    return store, uid, client, wid, cid, rid, challenge_id


# --- payload catalogue -------------------------------------------------------

def test_slice3_payload_catalogue_validates_and_rejects_malformed():
    assert validate_payload("challenge_answered", 1, {"challenge_id":"c","round_id":"r","claim_id":"cl","answer_version_id":"av","answer_text":"ans"}).author == "user"
    assert validate_payload("challenge_answered", 1, {"challenge_id":"c","round_id":"r","claim_id":"cl","answer_version_id":"av","answer_text":"ans","provisional_anchor_refs":["nf"]}).provisional_anchor_refs == ["nf"]
    with pytest.raises(ValidationError): validate_payload("challenge_answered", 1, {"challenge_id":"c","round_id":"r","claim_id":"cl","answer_version_id":"av","answer_text":""})
    assert validate_payload("challenge_deferred", 1, {"challenge_id":"c","round_id":"r","claim_id":"cl","reason":"r","condition":"later"}).condition == "later"
    with pytest.raises(ValidationError): validate_payload("challenge_deferred", 1, {"challenge_id":"c","round_id":"r","claim_id":"cl","reason":"","condition":"later"})
    with pytest.raises(ValidationError): validate_payload("challenge_deferred", 1, {"challenge_id":"c","round_id":"r","claim_id":"cl","reason":"r","condition":""})
    assert validate_payload("challenge_withdrawn", 1, {"challenge_id":"c","round_id":"r","claim_id":"cl","reason":"w"}).reason == "w"
    with pytest.raises(ValidationError): validate_payload("challenge_withdrawn", 1, {"challenge_id":"c","round_id":"r","claim_id":"cl","reason":""})
    assert validate_payload("verdict_confirmed", 1, {"round_id":"r","workspace_id":"w","claim_id":"cl","verdict_type":"circumstantial","user_reason":"x","revival_condition":"when measured"}).revival_condition == "when measured"
    with pytest.raises(ValidationError): validate_payload("verdict_confirmed", 1, {"round_id":"r","workspace_id":"w","claim_id":"cl","verdict_type":"circumstantial","user_reason":"x","revival_condition":None})
    with pytest.raises(ValidationError): validate_payload("verdict_confirmed", 1, {"round_id":"r","workspace_id":"w","claim_id":"cl","verdict_type":"survived","user_reason":"x","revival_condition":"later"})
    assert validate_payload("verdict_confirmed", 1, {"round_id":"r","workspace_id":"w","claim_id":"cl","verdict_type":"survived","user_reason":"x"}).revival_condition is None


# --- lifecycle ---------------------------------------------------------------

def test_answer_keeps_challenge_open_and_appends():
    store, uid, client, wid, cid, rid, chid = setup()
    first = client.post(f"/api/v2/challenges/{chid}/answers", json={"command_id":"a1", "expected_sequence":1, "answer_text":"my reply", "provisional_anchor_refs":["note-frag-1"]})
    assert first.status_code == 200
    ch = first.json()["fragment"]["challenges"][0]
    assert ch["status"] == "answered"
    assert ch["answers"] == [{"version_id": first.json()["result"]["answer_version_id"], "text":"my reply", "provisional_anchor_refs":["note-frag-1"], "sequence":1}]
    second = client.post(f"/api/v2/challenges/{chid}/answers", json={"command_id":"a2", "expected_sequence":2, "answer_text":"second reply", "provisional_anchor_refs":[]})
    assert second.status_code == 200
    assert len(second.json()["fragment"]["challenges"][0]["answers"]) == 2
    ws = client.get(f"/api/v2/workspaces/{wid}").json()
    assert chid in [c["id"] for c in ws["pending_challenges"]]
    home = client.get(f"/api/v2/universes/{uid}/home").json()
    assert chid in [f["id"] for f in home["pending_facts"]]


def test_defer_is_terminal_and_preserves_reason_condition():
    store, uid, client, wid, cid, rid, chid = setup()
    r = client.post(f"/api/v2/challenges/{chid}/defer", json={"command_id":"d", "expected_sequence":1, "reason":"need more evidence", "condition":"after Paper A"})
    assert r.status_code == 200
    ch = r.json()["fragment"]["challenges"][0]
    assert ch["status"] == "deferred" and ch["defer"] == {"reason":"need more evidence", "condition":"after Paper A"}
    assert client.post(f"/api/v2/challenges/{chid}/answers", json={"command_id":"a", "expected_sequence":2, "answer_text":"x"}).status_code == 409
    assert client.post(f"/api/v2/challenges/{chid}/defer", json={"command_id":"d2", "expected_sequence":2, "reason":"r", "condition":"c"}).status_code == 409
    assert client.post(f"/api/v2/challenges/{chid}/withdraw", json={"command_id":"wd", "expected_sequence":2, "reason":"r"}).status_code == 409
    ws = client.get(f"/api/v2/workspaces/{wid}").json()
    assert chid not in [c["id"] for c in ws["pending_challenges"]]


def test_withdraw_is_terminal_and_preserves_reason():
    store, uid, client, wid, cid, rid, chid = setup()
    r = client.post(f"/api/v2/challenges/{chid}/withdraw", json={"command_id":"wd", "expected_sequence":1, "reason":"no longer relevant"})
    assert r.status_code == 200
    ch = r.json()["fragment"]["challenges"][0]
    assert ch["status"] == "withdrawn" and ch["withdraw"] == {"reason":"no longer relevant"}
    assert client.post(f"/api/v2/challenges/{chid}/answers", json={"command_id":"a", "expected_sequence":2, "answer_text":"x"}).status_code == 409


def test_verdict_rolls_pending_and_answered_to_resolved_and_is_immutable():
    store, uid, client, wid, cid, rid, chid = setup()
    client.post(f"/api/v2/challenges/{chid}/answers", json={"command_id":"a", "expected_sequence":1, "answer_text":"reply", "provisional_anchor_refs":["nf"]})
    r = client.post(f"/api/v2/review-rounds/{rid}/verdicts", json={"command_id":"v", "expected_sequence":1, "verdict_type":"survived", "user_reason":"stood this round"})
    assert r.status_code == 200
    frag = r.json()["fragment"]
    assert frag["verdict"]["verdict_type"] == "survived" and frag["verdict"]["user_reason"] == "stood this round"
    assert frag["challenges"][0]["status"] == "resolved_by_verdict"
    ws = client.get(f"/api/v2/workspaces/{wid}").json()
    assert chid not in [c["id"] for c in ws["pending_challenges"]]
    assert client.post(f"/api/v2/review-rounds/{rid}/verdicts", json={"command_id":"v2", "expected_sequence":2, "verdict_type":"refuted", "user_reason":"x"}).status_code == 409
    assert client.post(f"/api/v2/challenges/{chid}/answers", json={"command_id":"a2", "expected_sequence":2, "answer_text":"late"}).status_code == 409


def test_circumstantial_verdict_requires_revival_condition_and_others_reject_it():
    store, uid, client, wid, cid, rid, chid = setup()
    ok = client.post(f"/api/v2/review-rounds/{rid}/verdicts", json={"command_id":"v", "expected_sequence":1, "verdict_type":"circumstantial", "user_reason":"x", "revival_condition":"when X is measured"})
    assert ok.status_code == 200 and ok.json()["fragment"]["verdict"]["revival_condition"] == "when X is measured"
    store2, uid2, client2, wid2, cid2, rid2, chid2 = setup()
    assert client2.post(f"/api/v2/review-rounds/{rid2}/verdicts", json={"command_id":"v", "expected_sequence":1, "verdict_type":"circumstantial", "user_reason":"x"}).status_code == 422
    store3, uid3, client3, wid3, cid3, rid3, chid3 = setup()
    assert client3.post(f"/api/v2/review-rounds/{rid3}/verdicts", json={"command_id":"v", "expected_sequence":1, "verdict_type":"refuted", "user_reason":"x", "revival_condition":"later"}).status_code == 422


def test_deferred_challenge_stays_terminal_after_round_verdict():
    store, uid, client, wid, cid, rid, chid = setup()
    client.post(f"/api/v2/challenges/{chid}/defer", json={"command_id":"d", "expected_sequence":1, "reason":"r", "condition":"c"})
    r = client.post(f"/api/v2/review-rounds/{rid}/verdicts", json={"command_id":"v", "expected_sequence":1, "verdict_type":"survived", "user_reason":"x"})
    ch = r.json()["fragment"]["challenges"][0]
    assert ch["status"] == "resolved_by_verdict" and ch["defer"] == {"reason":"r", "condition":"c"}
    assert client.post(f"/api/v2/challenges/{chid}/answers", json={"command_id":"a", "expected_sequence":3, "answer_text":"x"}).status_code == 409


# --- invalid transitions / 409 / 404 -----------------------------------------

def test_stale_expected_sequence_and_unknown_targets():
    store, uid, client, wid, cid, rid, chid = setup()
    assert client.post(f"/api/v2/challenges/{chid}/answers", json={"command_id":"a", "expected_sequence":0, "answer_text":"x"}).status_code == 409
    assert client.post("/api/v2/challenges/nope/answers", json={"command_id":"a", "expected_sequence":1, "answer_text":"x"}).status_code == 404
    assert client.post("/api/v2/challenges/nope/defer", json={"command_id":"d", "expected_sequence":1, "reason":"r", "condition":"c"}).status_code == 404
    assert client.post("/api/v2/challenges/nope/withdraw", json={"command_id":"w", "expected_sequence":1, "reason":"r"}).status_code == 404
    assert client.post("/api/v2/review-rounds/nope/verdicts", json={"command_id":"v", "expected_sequence":1, "verdict_type":"survived", "user_reason":"x"}).status_code == 404


def test_command_idempotency_no_duplicate_events():
    store, uid, client, wid, cid, rid, chid = setup()
    body = {"command_id":"a", "expected_sequence":1, "answer_text":"reply", "provisional_anchor_refs":[]}
    first = client.post(f"/api/v2/challenges/{chid}/answers", json=body).json()
    replay = client.post(f"/api/v2/challenges/{chid}/answers", json=body).json()
    assert first["result"] == replay["result"]
    assert len(store.read_events(uid)) == 5  # workspace, claim, round+challenge, answer


# --- re-review ---------------------------------------------------------------

def test_re_review_creates_new_round_and_preserves_old_verdict():
    store, uid, client, wid, cid, rid, chid = setup()
    client.post(f"/api/v2/review-rounds/{rid}/verdicts", json={"command_id":"v", "expected_sequence":1, "verdict_type":"boundary", "user_reason":"needs narrowing"})
    rnd2 = client.post(f"/api/v2/claims/{cid}/review-rounds", json={"command_id":"r2", "expected_sequence":0}).json()
    rid2 = rnd2["result"]["review_round_id"]
    assert rid2 != rid
    old = client.get(f"/api/v2/review-rounds/{rid}").json(); new = client.get(f"/api/v2/review-rounds/{rid2}").json()
    assert old["verdict"]["verdict_type"] == "boundary" and new["verdict"] is None
    assert old["challenges"][0]["status"] == "resolved_by_verdict" and new["challenges"][0]["status"] == "pending"
    assert {r["id"] for r in new["rounds"]} == {rid, rid2}
    assert next(r for r in new["rounds"] if r["id"] == rid)["verdict"]["verdict_type"] == "boundary"
    assert next(r for r in new["rounds"] if r["id"] == rid2)["verdict"] is None
    ws = client.get(f"/api/v2/workspaces/{wid}").json()
    assert len(ws["review_rounds"]) == 2 and all(r["verdict"] is not None or r["id"] == rid2 for r in ws["review_rounds"])


# --- no auto-verdict ---------------------------------------------------------

def test_nothing_emits_verdict_except_explicit_command():
    store, uid, client, wid, cid, rid, chid = setup()
    client.post(f"/api/v2/challenges/{chid}/answers", json={"command_id":"a", "expected_sequence":1, "answer_text":"reply"})
    client.post(f"/api/v2/challenges/{chid}/defer", json={"command_id":"d", "expected_sequence":2, "reason":"r", "condition":"c"})
    assert not any(e.event_type == "verdict_confirmed" for e in store.read_events(uid))


# --- projections -------------------------------------------------------------

def test_ledger_shape_and_workspace_home_drop_terminal():
    store, uid, client, wid, cid, rid, chid = setup()
    client.post(f"/api/v2/challenges/{chid}/answers", json={"command_id":"a", "expected_sequence":1, "answer_text":"reply", "provisional_anchor_refs":["nf-1"]})
    frag = client.get(f"/api/v2/review-rounds/{rid}").json()
    assert [c["id"] for c in frag["ledger"]["answered"]] == [chid]
    assert frag["ledger"]["pending"] == [] and frag["ledger"]["deferred"] == []
    assert [c["id"] for c in frag["ledger"]["brought_unconfirmed"]] == [chid]

    store2, uid2, client2, wid2, cid2, rid2, chid2 = setup()
    frag2 = client2.get(f"/api/v2/review-rounds/{rid2}").json()
    assert [c["id"] for c in frag2["ledger"]["pending"]] == [chid2]
    client2.post(f"/api/v2/challenges/{chid2}/defer", json={"command_id":"d", "expected_sequence":1, "reason":"r", "condition":"c"})
    frag2 = client2.get(f"/api/v2/review-rounds/{rid2}").json()
    assert [c["id"] for c in frag2["ledger"]["deferred"]] == [chid2] and frag2["ledger"]["pending"] == []

    assert chid in [f["id"] for f in client.get(f"/api/v2/universes/{uid}/home").json()["pending_facts"]]
    assert client.post(f"/api/v2/challenges/{chid}/defer", json={"command_id":"d2", "expected_sequence":2, "reason":"r", "condition":"c"}).status_code == 200
    assert chid not in [f["id"] for f in client.get(f"/api/v2/universes/{uid}/home").json()["pending_facts"]]
