"""Slice 4 real PostgreSQL material / evidence gate contract; requires CUI_TEST_DATABASE_URL."""
import os
import pytest
from alembic import command
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from cui.research_universe.api.routes import LibraryContext, LocalPrincipal, create_router
from cui.research_universe.api.slice1 import create_slice1_router
from cui.research_universe.api.slice2 import create_slice2_router
from cui.research_universe.api.slice3 import create_slice3_router
from cui.research_universe.api.slice4 import create_slice4_router
from cui.research_universe.application import ChallengeDraft, Slice1Service
from cui.research_universe.store.event_store import PostgresNativeEventStore
from cui.research_universe.store.sealed_park_store import PostgresSealedParkStore
from tests.pg_temp_db import temporary_database_url, drop_temporary_database
from pathlib import Path
from alembic.config import Config

PG_URL = os.getenv("CUI_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="No PG (set CUI_TEST_DATABASE_URL)")

class Generator:
    def generate(self, *, question, claim):
        return ChallengeDraft("causal gap", "why it matters", "seek a counterexample", "pg-fake-v4", "pg-fake", ["question", "claim"], "moderate")


def _alembic_config(url):
    config = Config(str(Path(__file__).parents[1] / "alembic.ini")); config.set_main_option("sqlalchemy.url", url); return config


@pytest.fixture()
def pg_slice4(monkeypatch):
    temp_url, database = temporary_database_url(PG_URL)
    monkeypatch.setenv("CUI_DATABASE_URL", temp_url); command.upgrade(_alembic_config(temp_url), "head")
    engine = create_engine(temp_url, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE sealed_park_commands, sealed_park_captures, ru_events, ru_commits, ru_streams, research_universes RESTART IDENTITY CASCADE"))
    store = PostgresNativeEventStore(engine); uid = store.create_active_universe("slice4-pg")
    principal = LocalPrincipal(); service = Slice1Service(store, principal.id, Generator()); ctx = LibraryContext("slice4-pg")
    app = FastAPI()
    app.include_router(create_router(store, ctx, principal), prefix="/api/v2")
    app.include_router(create_slice1_router(service, store, ctx, principal), prefix="/api/v2")
    app.include_router(create_slice2_router(service, store, PostgresSealedParkStore(engine), ctx, principal), prefix="/api/v2")
    app.include_router(create_slice3_router(service, store, ctx, principal), prefix="/api/v2")
    app.include_router(create_slice4_router(service, store, ctx, principal), prefix="/api/v2")
    yield engine, store, uid, TestClient(app), database
    engine.dispose(); drop_temporary_database(PG_URL, database)


def _tracer(c, uid):
    wid = c.post(f"/api/v2/universes/{uid}/workspaces", json={"command_id":"workspace","expected_sequence":0,"question":"Does X cause Y?"}).json()["result"]["workspace_id"]
    cid = c.post(f"/api/v2/workspaces/{wid}/claims", json={"command_id":"claim","expected_sequence":0,"text":"X causes Y."}).json()["result"]["claim_id"]
    rid = c.post(f"/api/v2/claims/{cid}/review-rounds", json={"command_id":"round","expected_sequence":0}).json()["result"]["review_round_id"]
    return wid, cid, rid


def test_pg_material_to_confirmed_contradiction_persists_and_replays(pg_slice4):
    engine, store, uid, c, database = pg_slice4
    wid, cid, rid = _tracer(c, uid)
    material = c.post(f"/api/v2/workspaces/{wid}/materials", json={"command_id":"material","expected_sequence":0,"excerpt":"Paper A observes Z.","source_locator":"Paper A","parse_status":"parsed","purpose":"evidence"})
    assert material.status_code == 201
    mid = material.json()["result"]["material_id"]
    propose = c.post(f"/api/v2/review-rounds/{rid}/evidence-candidates", json={"command_id":"propose","expected_sequence":0,"material_id":mid,"relation":"contradicts","uncertainty":"low"})
    assert propose.status_code == 201
    cand = propose.json()["result"]["candidate_id"]
    confirm = c.post(f"/api/v2/evidence-candidates/{cand}/confirm", json={"command_id":"confirm","expected_sequence":1,"user_reason":"I read the paper"})
    assert confirm.status_code == 200
    assert confirm.json()["result"]["challenge_id"]
    # second decision rejected after durable commit
    assert c.post(f"/api/v2/evidence-candidates/{cand}/confirm", json={"command_id":"confirm2","expected_sequence":2}).status_code == 409
    # replay from a fresh store over the same Postgres rows
    fresh = PostgresNativeEventStore(engine)
    events = fresh.read_events(uid)
    types = [e.event_type for e in events]
    assert types == ["workspace_created", "claim_created", "review_round_started", "challenge_created", "material_added", "evidence_relation_proposed", "evidence_relation_confirmed", "challenge_created"]
    from cui.research_universe.application import review_round_projection, workspace_projection, universe_home_projection
    frag = review_round_projection(fresh, uid, rid)
    assert frag["evidence_candidates"][0]["status"] == "confirmed"
    assert frag["evidence_candidates"][0]["material_anchor"]["excerpt"] == "Paper A observes Z."
    assert [f["relation"] for f in frag["confirmed_facts"]] == ["contradicts"]
    assert len(frag["challenges"]) == 2
    deterministic = [x for x in frag["challenges"] if x["provenance"]["prompt_version"] == "deterministic-evidence-contradiction-v1"]
    assert len(deterministic) == 1 and deterministic[0]["status"] == "pending"
    assert deterministic[0]["provenance"]["basis_refs"] == [mid, cand]
    ws = workspace_projection(fresh, uid, wid)
    assert ws["materials"][0]["excerpt"] == "Paper A observes Z."
    assert deterministic[0]["id"] in [x["id"] for x in ws["pending_challenges"]]
    assert deterministic[0]["id"] in [f["id"] for f in universe_home_projection(fresh, uid)["pending_facts"]]


def test_pg_reject_leaves_candidate_out_of_confirmed_facts(pg_slice4):
    engine, store, uid, c, database = pg_slice4
    wid, cid, rid = _tracer(c, uid)
    mid = c.post(f"/api/v2/workspaces/{wid}/materials", json={"command_id":"material","expected_sequence":0,"excerpt":"A note","source_locator":None,"parse_status":"parsed","purpose":"evidence"}).json()["result"]["material_id"]
    cand = c.post(f"/api/v2/review-rounds/{rid}/evidence-candidates", json={"command_id":"propose","expected_sequence":0,"material_id":mid,"relation":"supports"}).json()["result"]["candidate_id"]
    assert c.post(f"/api/v2/evidence-candidates/{cand}/reject", json={"command_id":"reject","expected_sequence":1,"user_reason":"misread"}).status_code == 200
    fresh = PostgresNativeEventStore(engine)
    from cui.research_universe.application import review_round_projection
    frag = review_round_projection(fresh, uid, rid)
    assert frag["evidence_candidates"][0]["status"] == "rejected" and frag["evidence_candidates"][0]["decision_reason"] == "misread"
    assert frag["confirmed_facts"] == []
