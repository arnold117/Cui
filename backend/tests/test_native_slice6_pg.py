"""Slice 6 real PostgreSQL contract — generated additional challenge + evidence
candidate persist and replay; requires CUI_TEST_DATABASE_URL."""
import os
import pytest
from alembic import command
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from pathlib import Path
from alembic.config import Config

from anneal.research_universe.api.routes import LibraryContext, LocalPrincipal, create_router
from anneal.research_universe.api.slice1 import create_slice1_router
from anneal.research_universe.api.slice2 import create_slice2_router
from anneal.research_universe.api.slice3 import create_slice3_router
from anneal.research_universe.api.slice4 import create_slice4_router
from anneal.research_universe.api.slice5 import create_slice5_router
from anneal.research_universe.api.slice6 import create_slice6_router
from anneal.research_universe.application import ChallengeDraft, EvidenceCandidateDraft, Slice1Service, review_round_projection
from anneal.research_universe.store.event_store import PostgresNativeEventStore
from anneal.research_universe.store.sealed_park_store import PostgresSealedParkStore
from tests.pg_temp_db import temporary_database_url, drop_temporary_database

PG_URL = os.getenv("CUI_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="No PG (set CUI_TEST_DATABASE_URL)")


class Generator:
    def generate(self, *, question, claim):
        return ChallengeDraft("causal gap", "why it matters", "seek a counterexample", "pg-slice1-fake", "pg-fake", ["question", "claim"], "moderate")
    def generate_additional(self, *, question, claim, prior_attack_surfaces):
        return ChallengeDraft("additional angle", "why it matters more", "test the additional angle", "slice6-expanded-challenge-v1", "pg-fake", ["review_round.question_snapshot", "review_round.claim_snapshot"], "moderate")


class EvidenceGenerator:
    def generate(self, *, claim, material_excerpt, parse_status):
        if parse_status == "failed":
            return EvidenceCandidateDraft("cannot_assess", "cannot read", None, "high", "slice6-evidence-candidate-v1", "pg-fake", [])
        return EvidenceCandidateDraft("contradicts", "it undercuts the claim", "the opposite effect", "moderate", "slice6-evidence-candidate-v1", "pg-fake", [])


def _alembic_config(url):
    config = Config(str(Path(__file__).parents[1] / "alembic.ini")); config.set_main_option("sqlalchemy.url", url); return config


@pytest.fixture()
def pg_slice6(monkeypatch):
    temp_url, database = temporary_database_url(PG_URL)
    monkeypatch.setenv("CUI_DATABASE_URL", temp_url); command.upgrade(_alembic_config(temp_url), "head")
    engine = create_engine(temp_url, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE sealed_park_commands, sealed_park_captures, ru_events, ru_commits, ru_streams, research_universes RESTART IDENTITY CASCADE"))
    store = PostgresNativeEventStore(engine); uid = store.create_active_universe("slice6-pg")
    principal = LocalPrincipal(); service = Slice1Service(store, principal.id, Generator(), EvidenceGenerator()); ctx = LibraryContext("slice6-pg")
    app = FastAPI()
    app.include_router(create_router(store, ctx, principal), prefix="/api/v2")
    app.include_router(create_slice1_router(service, store, ctx, principal), prefix="/api/v2")
    app.include_router(create_slice2_router(service, store, PostgresSealedParkStore(engine), ctx, principal), prefix="/api/v2")
    app.include_router(create_slice3_router(service, store, ctx, principal), prefix="/api/v2")
    app.include_router(create_slice4_router(service, store, ctx, principal), prefix="/api/v2")
    app.include_router(create_slice5_router(service, store, ctx, principal), prefix="/api/v2")
    app.include_router(create_slice6_router(service, store, ctx, principal), prefix="/api/v2")
    yield engine, store, uid, TestClient(app), database
    engine.dispose(); drop_temporary_database(PG_URL, database)


def test_pg_generated_additional_challenge_and_evidence_candidate_persist(pg_slice6):
    engine, store, uid, c, database = pg_slice6
    wid = c.post(f"/api/v2/universes/{uid}/workspaces", json={"command_id": "w", "expected_sequence": 0, "question": "Does X cause Y?"}).json()["result"]["workspace_id"]
    claim_id = c.post(f"/api/v2/workspaces/{wid}/claims", json={"command_id": "claim", "expected_sequence": 0, "text": "X causes Y."}).json()["result"]["claim_id"]
    rid = c.post(f"/api/v2/claims/{claim_id}/review-rounds", json={"command_id": "round", "expected_sequence": 0}).json()["result"]["review_round_id"]

    # generated additional challenge
    r = c.post(f"/api/v2/review-rounds/{rid}/challenges", json={"command_id": "extra", "expected_sequence": 0})
    assert r.status_code == 201
    extra_challenge_id = r.json()["result"]["challenge_id"]

    # generated evidence candidate on a parsed material
    mat = c.post(f"/api/v2/workspaces/{wid}/materials", json={"command_id": "m", "expected_sequence": 0, "excerpt": "The intervention shows the opposite effect.", "source_locator": "Paper A", "parse_status": "parsed", "purpose": "evidence"})
    assert mat.status_code == 201
    mid = mat.json()["result"]["material_id"]
    er = c.post(f"/api/v2/review-rounds/{rid}/evidence-candidate-generation", json={"command_id": "ev", "expected_sequence": 0, "material_id": mid})
    assert er.status_code == 201
    candidate_id = er.json()["result"]["candidate_id"]

    # generated evidence candidate on a failed-parse material -> forced cannot_assess
    fmat = c.post(f"/api/v2/workspaces/{wid}/materials", json={"command_id": "fm", "expected_sequence": 0, "excerpt": "garbled", "source_locator": None, "parse_status": "failed", "purpose": "evidence"})
    assert fmat.status_code == 201
    fmid = fmat.json()["result"]["material_id"]
    fe = c.post(f"/api/v2/review-rounds/{rid}/evidence-candidate-generation", json={"command_id": "fev", "expected_sequence": 0, "material_id": fmid})
    assert fe.status_code == 201
    failed_candidate_id = fe.json()["result"]["candidate_id"]

    # replay from a fresh store over the same Postgres rows
    fresh = PostgresNativeEventStore(engine)
    frag = review_round_projection(fresh, uid, rid)
    assert any(ch["id"] == extra_challenge_id and ch["provenance"]["prompt_version"] == "slice6-expanded-challenge-v1" for ch in frag["challenges"])
    by_id = {cand["id"]: cand for cand in frag["evidence_candidates"]}
    assert by_id[candidate_id]["relation"] == "contradicts"
    assert by_id[candidate_id]["provenance"]["generator_kind"] == "system"
    assert by_id[candidate_id]["provenance"]["prompt_version"] == "slice6-evidence-candidate-v1"
    assert by_id[candidate_id]["rationale"] == "it undercuts the claim"
    assert by_id[candidate_id]["evidence_highlight"] == "the opposite effect"
    assert by_id[failed_candidate_id]["relation"] == "cannot_assess"

    events = fresh.read_events(uid)
    assert not any(e.event_type == "verdict_confirmed" for e in events)
    assert not any(e.event_type == "direction_created" for e in events)
