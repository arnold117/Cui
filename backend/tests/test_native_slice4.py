"""Slice 4 manual material / evidence gate tests (in-memory domain/service/API)."""
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from cui.api.app import create_native_test_app
from cui.research_universe.application import ChallengeDraft
from cui.research_universe.domain.events import validate_payload
from cui.research_universe.store.event_store import InMemoryNativeEventStore


class FakeGenerator:
    def generate(self, *, question, claim):
        return ChallengeDraft("causal gap", "why it matters", "seek a counterexample", "fake-v1", "fake", ["question", "claim"], "moderate")


def setup():
    store = InMemoryNativeEventStore(); uid = store.create_active_universe("default")
    client = TestClient(create_native_test_app(store, challenge_generator=FakeGenerator()))
    wid = client.post(f"/api/v2/universes/{uid}/workspaces", json={"command_id":"w", "expected_sequence":0, "question":"Does X cause Y?"}).json()["result"]["workspace_id"]
    cid = client.post(f"/api/v2/workspaces/{wid}/claims", json={"command_id":"c", "expected_sequence":0, "text":"X causes Y."}).json()["result"]["claim_id"]
    rnd = client.post(f"/api/v2/claims/{cid}/review-rounds", json={"command_id":"r", "expected_sequence":0}).json()
    rid = rnd["result"]["review_round_id"]
    return store, uid, client, wid, cid, rid


def _add_material(client, wid, command_id="m", excerpt="Paper A observes Z.", source_locator="Paper A", parse_status="parsed", purpose="evidence", content_scope="full"):
    return client.post(f"/api/v2/workspaces/{wid}/materials", json={"command_id": command_id, "expected_sequence": 0, "excerpt": excerpt, "source_locator": source_locator, "parse_status": parse_status, "purpose": purpose, "content_scope": content_scope})


def _propose(client, rid, material_id, command_id="p", relation="contradicts", uncertainty=None):
    body = {"command_id": command_id, "expected_sequence": 0, "material_id": material_id, "relation": relation}
    if uncertainty is not None: body["uncertainty"] = uncertainty
    return client.post(f"/api/v2/review-rounds/{rid}/evidence-candidates", json=body)


# --- payload catalogue -------------------------------------------------------

def test_slice4_payload_catalogue_validates_and_rejects_malformed():
    assert validate_payload("material_added", 1, {"material_id":"m","workspace_id":"w","excerpt":"Paper A observes Z.","parse_status":"parsed","purpose":"evidence"}).excerpt == "Paper A observes Z."
    with pytest.raises(ValidationError): validate_payload("material_added", 1, {"material_id":"m","workspace_id":"w","excerpt":"","parse_status":"parsed","purpose":"evidence"})
    with pytest.raises(ValidationError): validate_payload("material_added", 1, {"material_id":"m","workspace_id":"w","excerpt":"x","parse_status":"bogus","purpose":"evidence"})
    with pytest.raises(ValidationError): validate_payload("material_added", 1, {"material_id":"m","workspace_id":"w","excerpt":"x","parse_status":"parsed","purpose":"bogus"})
    assert validate_payload("material_added", 1, {"material_id":"m","workspace_id":"w","excerpt":"x","parse_status":"failed","purpose":"reference","source_locator":"A"}).source_locator == "A"
    p = validate_payload("evidence_relation_proposed", 1, {"candidate_id":"c","round_id":"r","workspace_id":"w","claim_id":"cl","claim_version_id":"cv","claim_text":"X causes Y.","material_id":"m","material_excerpt":"A","material_source_locator":"Paper A","relation":"silent","uncertainty":"low"})
    assert p.relation == "silent" and p.generator_kind == "user" and p.basis_refs == []
    with pytest.raises(ValidationError): validate_payload("evidence_relation_proposed", 1, {"candidate_id":"c","round_id":"r","workspace_id":"w","claim_id":"cl","claim_version_id":"cv","claim_text":"X","material_id":"m","material_excerpt":"A","material_source_locator":None,"relation":"nope"})
    assert validate_payload("evidence_relation_confirmed", 1, {"candidate_id":"c","round_id":"r","claim_id":"cl","relation":"contradicts","user_reason":"seen"}).user_reason == "seen"
    with pytest.raises(ValidationError): validate_payload("evidence_relation_confirmed", 1, {"candidate_id":"c","round_id":"r","claim_id":"cl","relation":"bogus"})
    assert validate_payload("evidence_relation_corrected", 1, {"candidate_id":"c","round_id":"r","claim_id":"cl","prior_relation":"supports","corrected_relation":"contradicts"}).corrected_relation == "contradicts"
    with pytest.raises(ValidationError): validate_payload("evidence_relation_corrected", 1, {"candidate_id":"c","round_id":"r","claim_id":"cl","prior_relation":"supports","corrected_relation":"bogus"})
    assert validate_payload("evidence_relation_rejected", 1, {"candidate_id":"c","round_id":"r","claim_id":"cl","user_reason":"misread"}).user_reason == "misread"
    assert validate_payload("evidence_relation_withdrawn", 1, {"candidate_id":"c","round_id":"r","claim_id":"cl"}).user_reason is None


# --- material add ------------------------------------------------------------

def test_material_lands_neutrally_with_immutable_excerpt():
    store, uid, client, wid, cid, rid = setup()
    r = _add_material(client, wid)
    assert r.status_code == 201
    mat = r.json()["fragment"]["materials"][0]
    assert mat["excerpt"] == "Paper A observes Z." and mat["parse_status"] == "parsed" and mat["purpose"] == "evidence" and mat["source_locator"] == "Paper A"
    ws = client.get(f"/api/v2/workspaces/{wid}").json()
    assert [m["excerpt"] for m in ws["materials"]] == ["Paper A observes Z."]
    # immutable: the replayed event payload still carries the exact original excerpt
    event = next(e for e in store.read_events(uid) if e.event_type == "material_added")
    assert event.validated_payload().excerpt == "Paper A observes Z."


def test_reference_material_never_enters_candidate_flow():
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid, purpose="reference")
    material_id = client.get(f"/api/v2/workspaces/{wid}").json()["materials"][0]["id"]
    r = _propose(client, rid, material_id, relation="supports")
    assert r.status_code == 409


# --- candidate propose -------------------------------------------------------

def test_propose_snapshots_claim_and_material():
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid)
    material_id = client.get(f"/api/v2/workspaces/{wid}").json()["materials"][0]["id"]
    r = _propose(client, rid, material_id, relation="contradicts", uncertainty="moderate")
    assert r.status_code == 201
    cand = r.json()["fragment"]["evidence_candidates"][0]
    assert cand["status"] == "pending" and cand["relation"] == "contradicts" and cand["uncertainty"] == "moderate"
    assert cand["claim_snapshot"] == {"id": cid, "version_id": cand["claim_snapshot"]["version_id"], "text": "X causes Y."}
    assert cand["material_anchor"]["excerpt"] == "Paper A observes Z." and cand["material_anchor"]["source_locator"] == "Paper A"
    assert cand["provenance"]["generator_kind"] == "user"


def test_silent_requires_parsed_and_cannot_assess_allowed_for_failed():
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid, command_id="m-fail", parse_status="failed")
    material_id = client.get(f"/api/v2/workspaces/{wid}").json()["materials"][0]["id"]
    assert _propose(client, rid, material_id, command_id="p1", relation="silent").status_code == 409
    assert _propose(client, rid, material_id, command_id="p2", relation="cannot_assess").status_code == 201


def test_correct_cannot_turn_failed_parse_into_silent():
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid, command_id="m-fail", parse_status="failed"); _add_material(client, wid, command_id="m-ok", source_locator="Paper B")
    mids = {m["parse_status"]: m["id"] for m in client.get(f"/api/v2/workspaces/{wid}").json()["materials"]}
    failed = _propose(client, rid, mids["failed"], command_id="p1", relation="cannot_assess").json()["result"]["candidate_id"]
    parsed = _propose(client, rid, mids["parsed"], command_id="p2", relation="supports").json()["result"]["candidate_id"]
    before = len(store.read_events(uid))
    r = client.post(f"/api/v2/evidence-candidates/{failed}/correct", json={"command_id":"d1","expected_sequence":1,"corrected_relation":"silent"})
    assert r.status_code == 409 and "masquerade" in r.json()["detail"]
    assert len(store.read_events(uid)) == before
    # only silent is blocked: the same candidate can still be corrected to an assessable relation; parsed material may still go silent
    assert client.post(f"/api/v2/evidence-candidates/{failed}/correct", json={"command_id":"d2","expected_sequence":1,"corrected_relation":"supports"}).status_code == 200
    assert client.post(f"/api/v2/evidence-candidates/{parsed}/correct", json={"command_id":"d3","expected_sequence":1,"corrected_relation":"silent"}).status_code == 200


def test_propose_unknown_round_or_material_is_not_found():
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid)
    material_id = client.get(f"/api/v2/workspaces/{wid}").json()["materials"][0]["id"]
    assert _propose(client, "nope", material_id).status_code == 404
    assert _propose(client, rid, "nope").status_code == 404


# --- lifecycle ---------------------------------------------------------------

def test_candidate_lifecycle_each_terminal_and_immutable():
    # confirm
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid); mid = client.get(f"/api/v2/workspaces/{wid}").json()["materials"][0]["id"]
    _propose(client, rid, mid, command_id="p", relation="contradicts")
    cand = client.get(f"/api/v2/review-rounds/{rid}").json()["evidence_candidates"][0]
    r = client.post(f"/api/v2/evidence-candidates/{cand['id']}/confirm", json={"command_id":"d","expected_sequence":1,"user_reason":"I saw it"})
    assert r.status_code == 200
    frag = r.json()["fragment"]
    confirmed = next(c for c in frag["evidence_candidates"] if c["id"] == cand["id"])
    assert confirmed["status"] == "confirmed" and confirmed["relation"] == "contradicts" and confirmed["decision_reason"] == "I saw it"
    assert [f["id"] for f in frag["confirmed_facts"]] == [cand["id"]]
    # a second decision on the same candidate is a boundary violation
    assert client.post(f"/api/v2/evidence-candidates/{cand['id']}/confirm", json={"command_id":"d2","expected_sequence":2}).status_code == 409
    assert client.post(f"/api/v2/evidence-candidates/{cand['id']}/reject", json={"command_id":"d3","expected_sequence":2}).status_code == 409
    assert client.post(f"/api/v2/evidence-candidates/{cand['id']}/correct", json={"command_id":"d4","expected_sequence":2,"corrected_relation":"supports"}).status_code == 409
    assert client.post(f"/api/v2/evidence-candidates/{cand['id']}/withdraw", json={"command_id":"d5","expected_sequence":2}).status_code == 409

    # correct
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid); mid = client.get(f"/api/v2/workspaces/{wid}").json()["materials"][0]["id"]
    _propose(client, rid, mid, command_id="p", relation="supports")
    cand = client.get(f"/api/v2/review-rounds/{rid}").json()["evidence_candidates"][0]
    r = client.post(f"/api/v2/evidence-candidates/{cand['id']}/correct", json={"command_id":"d","expected_sequence":1,"corrected_relation":"silent","user_reason":"it does not address the claim"})
    assert r.status_code == 200
    corrected = next(c for c in r.json()["fragment"]["evidence_candidates"] if c["id"] == cand["id"])
    assert corrected["status"] == "corrected" and corrected["relation"] == "silent" and corrected["prior_relation"] == "supports"
    assert [f["relation"] for f in r.json()["fragment"]["confirmed_facts"]] == ["silent"]
    # correcting to the same relation is refused
    assert client.post(f"/api/v2/evidence-candidates/{cand['id']}/correct", json={"command_id":"d2","expected_sequence":2,"corrected_relation":"silent"}).status_code == 409

    # reject
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid); mid = client.get(f"/api/v2/workspaces/{wid}").json()["materials"][0]["id"]
    _propose(client, rid, mid, command_id="p", relation="contradicts")
    cand = client.get(f"/api/v2/review-rounds/{rid}").json()["evidence_candidates"][0]
    r = client.post(f"/api/v2/evidence-candidates/{cand['id']}/reject", json={"command_id":"d","expected_sequence":1,"user_reason":"misread"})
    assert r.status_code == 200
    rejected = next(c for c in r.json()["fragment"]["evidence_candidates"] if c["id"] == cand["id"])
    assert rejected["status"] == "rejected" and rejected["decision_reason"] == "misread"
    assert r.json()["fragment"]["confirmed_facts"] == []

    # withdraw
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid); mid = client.get(f"/api/v2/workspaces/{wid}").json()["materials"][0]["id"]
    _propose(client, rid, mid, command_id="p", relation="cannot_assess")
    cand = client.get(f"/api/v2/review-rounds/{rid}").json()["evidence_candidates"][0]
    r = client.post(f"/api/v2/evidence-candidates/{cand['id']}/withdraw", json={"command_id":"d","expected_sequence":1,"user_reason":"no longer relevant"})
    assert r.status_code == 200
    withdrawn = next(c for c in r.json()["fragment"]["evidence_candidates"] if c["id"] == cand["id"])
    assert withdrawn["status"] == "withdrawn" and withdrawn["decision_reason"] == "no longer relevant"
    assert r.json()["fragment"]["confirmed_facts"] == []


# --- confirmed contradiction -> deterministic challenge -----------------------

def test_confirm_contradiction_creates_deterministic_challenge_atomically():
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid); mid = client.get(f"/api/v2/workspaces/{wid}").json()["materials"][0]["id"]
    _propose(client, rid, mid, command_id="p", relation="contradicts")
    cand = client.get(f"/api/v2/review-rounds/{rid}").json()["evidence_candidates"][0]
    before = len(store.read_events(uid))
    r = client.post(f"/api/v2/evidence-candidates/{cand['id']}/confirm", json={"command_id":"d","expected_sequence":1})
    assert r.status_code == 200
    # one commit appends BOTH the confirmed event and the challenge_created event
    events = store.read_events(uid)
    assert len(events) == before + 2
    assert any(e.event_type == "evidence_relation_confirmed" for e in events)
    created = [e for e in events if e.event_type == "challenge_created" and e.validated_payload().prompt_version == "deterministic-evidence-contradiction-v2"]
    assert len(created) == 1
    cp = created[0].validated_payload()
    assert cp.generator_kind == "system" and cp.prompt_version == "deterministic-evidence-contradiction-v2" and cp.model_identifier is None
    assert cp.basis_refs == [mid, cand["id"]] and cp.uncertainty == "已确认取证事实"
    assert "已确认反证" in cp.attack_surface and cp.title == "已确认反证：Paper A"
    # the deterministic challenge appears in the round challenges and workspace pending facts
    frag = r.json()["fragment"]
    assert created[0].aggregate_id in [c["id"] for c in frag["challenges"]]
    ws = client.get(f"/api/v2/workspaces/{wid}").json()
    assert created[0].aggregate_id in [c["id"] for c in ws["pending_challenges"]]


def test_correct_to_contradiction_creates_deterministic_challenge():
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid); mid = client.get(f"/api/v2/workspaces/{wid}").json()["materials"][0]["id"]
    _propose(client, rid, mid, command_id="p", relation="supports")
    cand = client.get(f"/api/v2/review-rounds/{rid}").json()["evidence_candidates"][0]
    before = len(store.read_events(uid))
    r = client.post(f"/api/v2/evidence-candidates/{cand['id']}/correct", json={"command_id":"d","expected_sequence":1,"corrected_relation":"contradicts"})
    assert r.status_code == 200
    assert len(store.read_events(uid)) == before + 2
    created = [e for e in store.read_events(uid) if e.event_type == "challenge_created" and e.validated_payload().prompt_version == "deterministic-evidence-contradiction-v2"]
    assert len(created) == 1 and created[0].validated_payload().generator_kind == "system"


def test_deterministic_title_truncates_locator_and_falls_back_to_excerpt_first_line():
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid, command_id="m1", source_locator="A Very Long Paper Title That Keeps Going On")
    _add_material(client, wid, command_id="m2", source_locator=None, excerpt="  第一行就是这段材料的名字\n第二行不进标题")
    titles = []
    for i, m in enumerate(client.get(f"/api/v2/workspaces/{wid}").json()["materials"]):
        _propose(client, rid, m["id"], command_id=f"p{i}", relation="contradicts")
        cand = next(c for c in client.get(f"/api/v2/review-rounds/{rid}").json()["evidence_candidates"] if c["material_anchor"]["id"] == m["id"])
        r = client.post(f"/api/v2/evidence-candidates/{cand['id']}/confirm", json={"command_id": f"d{i}", "expected_sequence": 1})
        titles.append(next(c["title"] for c in r.json()["fragment"]["challenges"] if c["id"] == r.json()["result"]["challenge_id"]))
    assert sorted(titles) == sorted(["已确认反证：A Very Long Paper Title…", "已确认反证：第一行就是这段材料的名字"])


def test_non_contradiction_confirm_does_not_create_challenge_and_nothing_verdicts():
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid); mid = client.get(f"/api/v2/workspaces/{wid}").json()["materials"][0]["id"]
    _propose(client, rid, mid, command_id="p", relation="supports")
    cand = client.get(f"/api/v2/review-rounds/{rid}").json()["evidence_candidates"][0]
    before = len(store.read_events(uid))
    r = client.post(f"/api/v2/evidence-candidates/{cand['id']}/confirm", json={"command_id":"d","expected_sequence":1})
    assert r.status_code == 200
    assert len(store.read_events(uid)) == before + 1
    assert not any(e.event_type == "challenge_created" and e.validated_payload().prompt_version == "deterministic-evidence-contradiction-v2" for e in store.read_events(uid))
    # no auto-verdict anywhere in the slice
    assert not any(e.event_type == "verdict_confirmed" for e in store.read_events(uid))
    assert r.json()["fragment"]["verdict"] is None


# --- projections -------------------------------------------------------------

def test_workspace_materials_round_candidates_and_confirmed_facts_projection():
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid, command_id="m1", excerpt="supports excerpt", purpose="evidence")
    _add_material(client, wid, command_id="m2", excerpt="ref only", purpose="reference")
    ws = client.get(f"/api/v2/workspaces/{wid}").json()
    assert {m["excerpt"] for m in ws["materials"]} == {"supports excerpt", "ref only"}
    by_excerpt = {m["excerpt"]: m for m in ws["materials"]}
    mid = by_excerpt["supports excerpt"]["id"]
    _propose(client, rid, mid, command_id="p", relation="supports")
    cand = client.get(f"/api/v2/review-rounds/{rid}").json()["evidence_candidates"][0]
    client.post(f"/api/v2/evidence-candidates/{cand['id']}/confirm", json={"command_id":"d","expected_sequence":1})
    frag = client.get(f"/api/v2/review-rounds/{rid}").json()
    assert len(frag["evidence_candidates"]) == 1 and frag["evidence_candidates"][0]["status"] == "confirmed"
    assert [f["id"] for f in frag["confirmed_facts"]] == [cand["id"]]
    # rejected/withdrawn never join confirmed facts
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid, command_id="m1", excerpt="e", purpose="evidence")
    mid = client.get(f"/api/v2/workspaces/{wid}").json()["materials"][0]["id"]
    _propose(client, rid, mid, command_id="p", relation="supports")
    cand = client.get(f"/api/v2/review-rounds/{rid}").json()["evidence_candidates"][0]
    client.post(f"/api/v2/evidence-candidates/{cand['id']}/reject", json={"command_id":"d","expected_sequence":1})
    frag = client.get(f"/api/v2/review-rounds/{rid}").json()
    assert frag["evidence_candidates"][0]["status"] == "rejected" and frag["confirmed_facts"] == []


# --- API integration / 409 / 404 ---------------------------------------------

def test_stale_expected_sequence_and_unknown_targets():
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid); mid = client.get(f"/api/v2/workspaces/{wid}").json()["materials"][0]["id"]
    _propose(client, rid, mid, command_id="p", relation="contradicts")
    cand = client.get(f"/api/v2/review-rounds/{rid}").json()["evidence_candidates"][0]
    # stale expected_sequence on a decision command (candidate stream is at sequence 1)
    assert client.post(f"/api/v2/evidence-candidates/{cand['id']}/confirm", json={"command_id":"d","expected_sequence":0}).status_code == 409
    assert client.post("/api/v2/workspaces/nope/materials", json={"command_id":"m","expected_sequence":0,"excerpt":"x","parse_status":"parsed","purpose":"evidence"}).status_code == 404
    assert client.post("/api/v2/review-rounds/nope/evidence-candidates", json={"command_id":"p","expected_sequence":0,"material_id":mid,"relation":"supports"}).status_code == 404
    assert client.post("/api/v2/evidence-candidates/nope/confirm", json={"command_id":"d","expected_sequence":1}).status_code == 404
    assert client.post("/api/v2/evidence-candidates/nope/correct", json={"command_id":"d","expected_sequence":1,"corrected_relation":"supports"}).status_code == 404
    assert client.post("/api/v2/evidence-candidates/nope/reject", json={"command_id":"d","expected_sequence":1}).status_code == 404
    assert client.post("/api/v2/evidence-candidates/nope/withdraw", json={"command_id":"d","expected_sequence":1}).status_code == 404


def test_command_idempotency_no_duplicate_events():
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid); mid = client.get(f"/api/v2/workspaces/{wid}").json()["materials"][0]["id"]
    _propose(client, rid, mid, command_id="p", relation="contradicts")
    cand = client.get(f"/api/v2/review-rounds/{rid}").json()["evidence_candidates"][0]
    body = {"command_id":"d","expected_sequence":1}
    first = client.post(f"/api/v2/evidence-candidates/{cand['id']}/confirm", json=body).json()
    replay = client.post(f"/api/v2/evidence-candidates/{cand['id']}/confirm", json=body).json()
    assert first["result"] == replay["result"]
    assert len([e for e in store.read_events(uid) if e.event_type == "evidence_relation_confirmed"]) == 1
    assert len([e for e in store.read_events(uid) if e.event_type == "challenge_created" and e.validated_payload().prompt_version == "deterministic-evidence-contradiction-v2"]) == 1


def test_reference_material_proposal_and_silent_failed_are_409():
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid, command_id="m1", purpose="reference")
    _add_material(client, wid, command_id="m2", parse_status="failed")
    ws = client.get(f"/api/v2/workspaces/{wid}").json()
    by_purpose = {m["purpose"]: m for m in ws["materials"]}
    assert _propose(client, rid, by_purpose["reference"]["id"], command_id="p1", relation="supports").status_code == 409
    assert _propose(client, rid, by_purpose["evidence"]["id"], command_id="p2", relation="silent").status_code == 409
    assert _propose(client, rid, by_purpose["evidence"]["id"], command_id="p3", relation="cannot_assess").status_code == 201


# --- S4 (#24): bring into evidence desk = dedup by locator; answer refs are validated (E3) ---

def test_same_locator_evidence_dedups_without_event_but_null_locator_and_reference_never_do():
    store, uid, client, wid, cid, rid = setup()
    first = _add_material(client, wid, command_id="m1", content_scope="abstract").json()
    mid = first["result"]["material_id"]
    before = len(store.read_events(uid))
    again = _add_material(client, wid, command_id="m2", excerpt="A re-fetched abstract.")
    assert again.status_code == 201 and again.json()["event_ids"] == []
    assert again.json()["result"] == {"material_id": mid, "workspace_id": wid, "deduplicated": True}
    assert len(store.read_events(uid)) == before
    # retrying the SAME command is an idempotent replay of the original commit, not a dedup
    replay = _add_material(client, wid, command_id="m1", content_scope="abstract").json()
    assert replay["event_ids"] == first["event_ids"] and "deduplicated" not in replay["result"]
    other = _add_material(client, wid, command_id="m3", source_locator="Paper B").json()["result"]["material_id"]
    ref = _add_material(client, wid, command_id="m4", purpose="reference").json()["result"]["material_id"]
    n1 = _add_material(client, wid, command_id="n1", source_locator=None).json()["result"]["material_id"]
    n2 = _add_material(client, wid, command_id="n2", source_locator=None).json()["result"]["material_id"]
    assert len({mid, other, ref, n1, n2}) == 5
    mats = client.get(f"/api/v2/workspaces/{wid}").json()["materials"]
    assert [(m["id"], m["content_scope"]) for m in mats] == [(mid, "abstract"), (other, "full"), (ref, "full"), (n1, "full"), (n2, "full")]
    assert mats[0]["excerpt"] == "Paper A observes Z."  # first snapshot kept, never updated
    # a failed parse never blocks a later parsed one; the parsed one is what dedups afterwards
    failed = _add_material(client, wid, command_id="fx", source_locator="Paper X", parse_status="failed").json()["result"]["material_id"]
    before = len(store.read_events(uid))
    parsed = _add_material(client, wid, command_id="px", source_locator="Paper X").json()
    assert parsed["result"]["material_id"] != failed and len(parsed["event_ids"]) == 1 and len(store.read_events(uid)) == before + 1
    assert _add_material(client, wid, command_id="px2", source_locator="Paper X").json()["result"] == {"material_id": parsed["result"]["material_id"], "workspace_id": wid, "deduplicated": True}


def test_answer_refs_must_be_this_workspaces_material_or_anchor():
    store, uid, client, wid, cid, rid = setup()
    chid = client.get(f"/api/v2/review-rounds/{rid}").json()["challenges"][0]["id"]
    evidence = _add_material(client, wid, command_id="me").json()["result"]["material_id"]
    reference = _add_material(client, wid, command_id="mr", source_locator="Paper R", purpose="reference").json()["result"]["material_id"]
    note = client.post(f"/api/v2/workspaces/{wid}/notes", json={"command_id": "n", "expected_sequence": 1, "text": "A useful fragment."}).json()["result"]
    anchor = client.post(f"/api/v2/workspaces/{wid}/anchors", json={"command_id": "an", "expected_sequence": 2, "note_id": note["note_id"], "note_revision_id": note["note_revision_id"], "start": 0, "end": 6, "selected_text": "A usef"}).json()["result"]["anchor_id"]
    other_wid = client.post(f"/api/v2/universes/{uid}/workspaces", json={"command_id": "w2", "expected_sequence": 0, "question": "Another question?"}).json()["result"]["workspace_id"]
    foreign = _add_material(client, other_wid, command_id="mf").json()["result"]["material_id"]
    before = len(store.read_events(uid))
    for i, refs in enumerate([["nope"], [foreign], [evidence, "nope"]]):
        r = client.post(f"/api/v2/challenges/{chid}/answers", json={"command_id": f"bad{i}", "expected_sequence": 1, "answer_text": "reply", "provisional_anchor_refs": refs})
        assert r.status_code == 409, refs
    assert len(store.read_events(uid)) == before
    ok = client.post(f"/api/v2/challenges/{chid}/answers", json={"command_id": "ok", "expected_sequence": 1, "answer_text": "reply", "provisional_anchor_refs": [evidence, reference, anchor]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["fragment"]["challenges"][0]["answers"][0]["provisional_anchor_refs"] == [evidence, reference, anchor]
    assert [c["id"] for c in ok.json()["fragment"]["ledger"]["brought_unconfirmed"]] == [chid]
