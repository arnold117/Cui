"""Slice 6 expanded LLM evidence candidates / additional challenges (in-memory).

Covers: payload catalogue (rationale/evidence_highlight optional), the two
explicit generation commands, the failed-parse iron rule, the shared decision
lifecycle, no-auto-anything, API integration (happy path + 409/404), and the
canary harness exercised with mock generators.
"""
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from anneal.api.app import create_native_test_app
from anneal.research_universe.application import ChallengeDraft, EvidenceCandidateDraft
from anneal.research_universe.domain.events import validate_payload
from anneal.research_universe.store.event_store import InMemoryNativeEventStore


def _has_cjk(text: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in text)


class FakeGenerator:
    """Slice 1 generate + Slice 6 generate_additional. Records what it was fed."""
    def __init__(self, language: str = "zh", fail: bool = False) -> None:
        self.language, self.fail = language, fail
        self.seen_surfaces: list[list[str]] = []
        self.seen_questions: list[str] = []

    def generate(self, *, question, claim):
        return ChallengeDraft("第一个攻击面", "为何重要", "自检方法", "slice1-narrow-challenge-v1", "fake", ["review_round.question_snapshot", "review_round.claim_snapshot"], "中等")

    def generate_additional(self, *, question, claim, prior_attack_surfaces):
        self.seen_questions.append(question)
        self.seen_surfaces.append(list(prior_attack_surfaces))
        if self.fail:
            raise ValueError("schema broke")
        if self.language == "en":
            surface, why, method = "A missing control group", "Why it matters", "Self-check method"
        else:
            surface, why, method = "缺少对照组", "为何重要", "自检方法"
        return ChallengeDraft(surface, why, method, "slice6-expanded-challenge-v1", "fake", ["review_round.question_snapshot", "review_round.claim_snapshot"], "中等")


class FakeEvidenceGenerator:
    def __init__(self, relation: str = "contradicts", rationale: str | None = None, highlight: str | None = None, language: str = "zh") -> None:
        self.relation, self.rationale, self.highlight, self.language = relation, rationale, highlight, language
        self.seen_parse_status: list[str] = []
        self.seen_excerpts: list[str] = []

    def generate(self, *, claim, material_excerpt, parse_status):
        self.seen_parse_status.append(parse_status)
        self.seen_excerpts.append(material_excerpt)
        if self.language == "en":
            rationale = self.rationale or "The excerpt undercuts the claim."
        else:
            rationale = self.rationale or "这段摘录与 claim 构成反证。"
        return EvidenceCandidateDraft(self.relation, rationale, self.highlight, "中", "slice6-evidence-candidate-v1", "fake", [])


def setup(generator=None, evidence_generator=None):
    store = InMemoryNativeEventStore(); uid = store.create_active_universe("default")
    client = TestClient(create_native_test_app(store, challenge_generator=generator or FakeGenerator(), evidence_generator=evidence_generator or FakeEvidenceGenerator()))
    wid = client.post(f"/api/v2/universes/{uid}/workspaces", json={"command_id":"w", "expected_sequence":0, "question":"Does X cause Y?"}).json()["result"]["workspace_id"]
    cid = client.post(f"/api/v2/workspaces/{wid}/claims", json={"command_id":"c", "expected_sequence":0, "text":"X causes Y."}).json()["result"]["claim_id"]
    rid = client.post(f"/api/v2/claims/{cid}/review-rounds", json={"command_id":"r", "expected_sequence":0}).json()["result"]["review_round_id"]
    return store, uid, client, wid, cid, rid


def _add_material(client, wid, command_id="m", excerpt="Paper A observes Z.", parse_status="parsed", purpose="evidence"):
    return client.post(f"/api/v2/workspaces/{wid}/materials", json={"command_id": command_id, "expected_sequence": 0, "excerpt": excerpt, "source_locator": "Paper A", "parse_status": parse_status, "purpose": purpose})


def _material_id(client, wid):
    return client.get(f"/api/v2/workspaces/{wid}").json()["materials"][0]["id"]


def _gen_challenge(client, rid, command_id="g", expected_sequence=0):
    return client.post(f"/api/v2/review-rounds/{rid}/challenges", json={"command_id": command_id, "expected_sequence": expected_sequence})


def _gen_evidence(client, rid, material_id, command_id="g", expected_sequence=0):
    return client.post(f"/api/v2/review-rounds/{rid}/evidence-candidate-generation", json={"command_id": command_id, "expected_sequence": expected_sequence, "material_id": material_id})


# --- payload catalogue -------------------------------------------------------

def test_slice6_payload_catalogue_rationale_highlight_optional():
    old = validate_payload("evidence_relation_proposed", 1, {"candidate_id":"c","round_id":"r","workspace_id":"w","claim_id":"cl","claim_version_id":"cv","claim_text":"X causes Y.","material_id":"m","material_excerpt":"A","material_source_locator":"Paper A","relation":"silent","uncertainty":"low"})
    assert old.rationale is None and old.evidence_highlight is None
    new = validate_payload("evidence_relation_proposed", 1, {"candidate_id":"c","round_id":"r","workspace_id":"w","claim_id":"cl","claim_version_id":"cv","claim_text":"X causes Y.","material_id":"m","material_excerpt":"A","material_source_locator":"Paper A","relation":"supports","uncertainty":"moderate","rationale":"it corroborates","evidence_highlight":"observes Z","generator_kind":"system","prompt_version":"slice6-evidence-candidate-v1","model_identifier":"m1","basis_refs":["m"]})
    assert new.rationale == "it corroborates" and new.evidence_highlight == "observes Z"
    assert new.generator_kind == "system" and new.prompt_version == "slice6-evidence-candidate-v1"
    with pytest.raises(ValidationError): validate_payload("evidence_relation_proposed", 1, {"candidate_id":"c","round_id":"r","workspace_id":"w","claim_id":"cl","claim_version_id":"cv","claim_text":"X","material_id":"m","material_excerpt":"A","relation":"nope"})


# --- generate_additional_challenge --------------------------------------------

def test_generate_additional_challenge_creates_distinct_system_challenge():
    store, uid, client, wid, cid, rid = setup()
    before = len(store.read_events(uid))
    r = _gen_challenge(client, rid)
    assert r.status_code == 201
    assert len(store.read_events(uid)) == before + 1
    created = [e for e in store.read_events(uid) if e.event_type == "challenge_created" and e.validated_payload().prompt_version == "slice6-expanded-challenge-v1"]
    assert len(created) == 1
    cp = created[0].validated_payload()
    assert cp.generator_kind == "system" and cp.model_identifier == "fake"
    assert cp.attack_surface == "缺少对照组"
    first = next(e.validated_payload() for e in store.read_events(uid) if e.event_type == "challenge_created" and e.validated_payload().prompt_version == "slice1-narrow-challenge-v1")
    assert cp.challenge_id != first.challenge_id
    frag = r.json()["fragment"]
    assert len(frag["challenges"]) == 2
    assert frag["challenges"][0]["id"] != frag["challenges"][1]["id"]


def test_generate_additional_challenge_language_follows_claim():
    # English claim -> the mock (language=en) returns English; assert no CJK leaks.
    store, uid, client, wid, cid, rid = setup(generator=FakeGenerator(language="en"))
    # seed an English claim
    wid = client.post(f"/api/v2/universes/{uid}/workspaces", json={"command_id":"w2", "expected_sequence":0, "question":"Why does X cause Y?"}).json()["result"]["workspace_id"]
    cid = client.post(f"/api/v2/workspaces/{wid}/claims", json={"command_id":"c2", "expected_sequence":0, "text":"X causes Y in healthy adults."}).json()["result"]["claim_id"]
    rid = client.post(f"/api/v2/claims/{cid}/review-rounds", json={"command_id":"r2", "expected_sequence":0}).json()["result"]["review_round_id"]
    r = _gen_challenge(client, rid, command_id="gen-en")
    assert r.status_code == 201
    added = [c for c in r.json()["fragment"]["challenges"] if c["provenance"]["prompt_version"] == "slice6-expanded-challenge-v1"][0]
    assert added["attack_surface"] == "A missing control group" and not _has_cjk(added["attack_surface"])


def test_generate_additional_passes_existing_attack_surfaces():
    gen = FakeGenerator()
    store, uid, client, wid, cid, rid = setup(generator=gen)
    _gen_challenge(client, rid, command_id="g1")
    _gen_challenge(client, rid, command_id="g2")
    assert gen.seen_surfaces == [["第一个攻击面"], ["第一个攻击面", "缺少对照组"]]
    assert gen.seen_questions == ["Does X cause Y?", "Does X cause Y?"]


def test_generate_additional_llm_schema_failure_commits_nothing():
    store, uid, client, wid, cid, rid = setup(generator=FakeGenerator(fail=True))
    before = len(store.read_events(uid))
    r = _gen_challenge(client, rid)
    assert r.status_code == 502
    assert len(store.read_events(uid)) == before


# --- generate_evidence_candidate ---------------------------------------------

def test_generate_evidence_candidate_creates_candidate_with_provenance():
    evg = FakeEvidenceGenerator(relation="contradicts", highlight="observes Z")
    store, uid, client, wid, cid, rid = setup(evidence_generator=evg)
    _add_material(client, wid)
    mid = _material_id(client, wid)
    before = len(store.read_events(uid))
    r = _gen_evidence(client, rid, mid)
    assert r.status_code == 201
    assert len(store.read_events(uid)) == before + 1
    cand = r.json()["fragment"]["evidence_candidates"][0]
    assert cand["status"] == "pending" and cand["relation"] == "contradicts"
    assert cand["rationale"] == "这段摘录与 claim 构成反证。" and cand["evidence_highlight"] == "observes Z"
    assert cand["provenance"]["generator_kind"] == "system"
    assert cand["provenance"]["prompt_version"] == "slice6-evidence-candidate-v1"
    assert cand["provenance"]["model_identifier"] == "fake"
    assert cand["provenance"]["basis_refs"] == [mid]
    assert cand["material_anchor"]["excerpt"] == "Paper A observes Z."
    ep = [e for e in store.read_events(uid) if e.event_type == "evidence_relation_proposed"][-1].validated_payload()
    assert ep.generator_kind == "system" and ep.prompt_version == "slice6-evidence-candidate-v1"
    assert ep.rationale == "这段摘录与 claim 构成反证。" and ep.evidence_highlight == "observes Z"


def test_generate_evidence_failed_parse_forces_cannot_assess_even_if_silent():
    evg = FakeEvidenceGenerator(relation="silent")
    store, uid, client, wid, cid, rid = setup(evidence_generator=evg)
    _add_material(client, wid, command_id="m-fail", parse_status="failed")
    mid = _material_id(client, wid)
    r = _gen_evidence(client, rid, mid)
    assert r.status_code == 201
    cand = r.json()["fragment"]["evidence_candidates"][0]
    assert cand["relation"] == "cannot_assess"
    ep = [e for e in store.read_events(uid) if e.event_type == "evidence_relation_proposed"][-1].validated_payload()
    assert ep.relation == "cannot_assess"
    assert evg.seen_parse_status == ["failed"]


def test_generate_evidence_reference_material_rejected():
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid, purpose="reference")
    mid = _material_id(client, wid)
    assert _gen_evidence(client, rid, mid).status_code == 409


def test_generate_evidence_unknown_round_or_material_404():
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid)
    mid = _material_id(client, wid)
    assert _gen_evidence(client, "nope", mid).status_code == 404
    assert _gen_evidence(client, rid, "nope").status_code == 404


def test_generated_candidate_enters_normal_decision_lifecycle():
    store, uid, client, wid, cid, rid = setup(evidence_generator=FakeEvidenceGenerator(relation="contradicts"))
    _add_material(client, wid)
    mid = _material_id(client, wid)
    _gen_evidence(client, rid, mid)
    cand = client.get(f"/api/v2/review-rounds/{rid}").json()["evidence_candidates"][0]
    r = client.post(f"/api/v2/evidence-candidates/{cand['id']}/confirm", json={"command_id":"d","expected_sequence":1,"user_reason":"I checked it"})
    assert r.status_code == 200
    confirmed = next(c for c in r.json()["fragment"]["evidence_candidates"] if c["id"] == cand["id"])
    assert confirmed["status"] == "confirmed" and confirmed["decision_reason"] == "I checked it"
    assert [f["id"] for f in r.json()["fragment"]["confirmed_facts"]] == [cand["id"]]
    # a second decision is refused (immutable)
    assert client.post(f"/api/v2/evidence-candidates/{cand['id']}/reject", json={"command_id":"d2","expected_sequence":2}).status_code == 409


# --- no auto-anything ----------------------------------------------------------

def test_generation_never_auto_creates_verdict_claim_direction_or_workspace():
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid)
    mid = _material_id(client, wid)
    _gen_challenge(client, rid, command_id="g1")
    _gen_evidence(client, rid, mid, command_id="g2")
    events = store.read_events(uid)
    assert not any(e.event_type == "verdict_confirmed" for e in events)
    assert not any(e.event_type == "direction_created" for e in events)
    assert len([e for e in events if e.event_type == "claim_created"]) == 1
    assert len([e for e in events if e.event_type == "workspace_created"]) == 1


# --- API integration / 409 / 404 ----------------------------------------------

def test_generate_stale_expected_sequence_409():
    store, uid, client, wid, cid, rid = setup()
    assert _gen_challenge(client, rid, command_id="g1", expected_sequence=1).status_code == 409
    _add_material(client, wid)
    mid = _material_id(client, wid)
    assert _gen_evidence(client, rid, mid, command_id="g2", expected_sequence=1).status_code == 409


def test_generate_unknown_round_404_and_fingerprint_conflict_409():
    store, uid, client, wid, cid, rid = setup()
    _add_material(client, wid, command_id="m1")
    _add_material(client, wid, command_id="m2")
    ws = client.get(f"/api/v2/workspaces/{wid}").json()
    m1 = ws["materials"][0]["id"]; m2 = ws["materials"][1]["id"]
    assert _gen_challenge(client, "nope").status_code == 404
    assert _gen_evidence(client, "nope", m1).status_code == 404
    # same command_id with a different semantic payload -> fingerprint conflict
    assert _gen_evidence(client, rid, m1, command_id="dup").status_code == 201
    assert _gen_evidence(client, rid, m2, command_id="dup").status_code == 409


# --- canary harness with mock generators ---------------------------------------

def test_canary_harness_with_mocks():
    """The live canary's harness logic is exercised here with mock generators."""
    import importlib.util
    import sys
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "scripts" / "canary_native_slice6.py"
    spec = importlib.util.spec_from_file_location("canary_native_slice6", path)
    canary = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass can resolve the module namespace.
    sys.modules["canary_native_slice6"] = canary
    try:
        spec.loader.exec_module(canary)
    finally:
        sys.modules.pop("canary_native_slice6", None)

    class MockChallenge:
        def generate(self, *, question, claim):
            lang = "zh" if _has_cjk(claim) else "en"
            if lang == "zh":
                return ChallengeDraft("中文攻击面", "为何重要", "自检方法", "slice1-narrow-challenge-v1", "mock", ["question", "claim"], "中等")
            return ChallengeDraft("English surface", "Why", "Self-check", "slice1-narrow-challenge-v1", "mock", ["question", "claim"], "moderate")
        def generate_additional(self, *, question, claim, prior_attack_surfaces):
            lang = "zh" if _has_cjk(claim) else "en"
            if lang == "zh":
                return ChallengeDraft("另一个中文角度", "为何重要", "自检方法", "slice6-expanded-challenge-v1", "mock", ["question", "claim"], "中等")
            return ChallengeDraft("A second English angle", "Why", "Self-check", "slice6-expanded-challenge-v1", "mock", ["question", "claim"], "moderate")

    class MockEvidence:
        def generate(self, *, claim, material_excerpt, parse_status):
            lang = "zh" if _has_cjk(claim) else "en"
            if parse_status == "failed":
                return EvidenceCandidateDraft("cannot_assess", "无法判断", None, "中", "slice6-evidence-candidate-v1", "mock", [])
            if lang == "zh":
                return EvidenceCandidateDraft("supports", "这段摘录支持该 claim", "observes Z", "中", "slice6-evidence-candidate-v1", "mock", [])
            return EvidenceCandidateDraft("contradicts", "The excerpt undercuts the claim.", "shows the opposite", "moderate", "slice6-evidence-candidate-v1", "mock", [])

    results = []
    for case_id, _, fn in canary.CASES:
        outcome = canary.run_attempt(fn, MockChallenge(), MockEvidence())
        results.append((case_id, outcome))
        assert outcome.ok, f"{case_id} failed with mock generators: {outcome.actual} :: {outcome.detail}"
    assert len(results) == len(canary.CASES)
