"""Slice 3 real PostgreSQL review-lifecycle contract; requires CUI_TEST_DATABASE_URL."""
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
        return ChallengeDraft("causal gap", "why it matters", "seek a counterexample", "pg-fake-v3", "pg-fake", ["question", "claim"], "moderate")


def _alembic_config(url):
    config = Config(str(Path(__file__).parents[1] / "alembic.ini")); config.set_main_option("sqlalchemy.url", url); return config


@pytest.fixture()
def pg_slice3(monkeypatch):
    temp_url, database = temporary_database_url(PG_URL)
    monkeypatch.setenv("CUI_DATABASE_URL", temp_url); command.upgrade(_alembic_config(temp_url), "head")
    engine = create_engine(temp_url, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE sealed_park_commands, sealed_park_captures, ru_events, ru_commits, ru_streams, research_universes RESTART IDENTITY CASCADE"))
    store = PostgresNativeEventStore(engine); uid = store.create_active_universe("slice3-pg")
    principal = LocalPrincipal(); service = Slice1Service(store, principal.id, Generator()); ctx = LibraryContext("slice3-pg")
    app = FastAPI()
    app.include_router(create_router(store, ctx, principal), prefix="/api/v2")
    app.include_router(create_slice1_router(service, store, ctx, principal), prefix="/api/v2")
    app.include_router(create_slice2_router(service, store, PostgresSealedParkStore(engine), ctx, principal), prefix="/api/v2")
    app.include_router(create_slice3_router(service, store, ctx, principal), prefix="/api/v2")
    yield engine, store, uid, TestClient(app), database
    engine.dispose(); drop_temporary_database(PG_URL, database)


def _tracer(c, uid):
    wid = c.post(f"/api/v2/universes/{uid}/workspaces", json={"command_id":"workspace","expected_sequence":0,"question":"Does X cause Y?"}).json()["result"]["workspace_id"]
    cid = c.post(f"/api/v2/workspaces/{wid}/claims", json={"command_id":"claim","expected_sequence":0,"text":"X causes Y."}).json()["result"]["claim_id"]
    rnd = c.post(f"/api/v2/claims/{cid}/review-rounds", json={"command_id":"round","expected_sequence":0}).json()
    return wid, cid, rnd["result"]["review_round_id"], rnd["result"]["challenge_id"]


def test_pg_review_lifecycle_persists_and_replays(pg_slice3):
    engine, store, uid, c, database = pg_slice3
    wid, cid, rid, chid = _tracer(c, uid)
    assert c.post(f"/api/v2/challenges/{chid}/answers", json={"command_id":"a1","expected_sequence":1,"answer_text":"reply","provisional_anchor_refs":["nf-1"]}).status_code == 200
    assert c.post(f"/api/v2/challenges/{chid}/answers", json={"command_id":"a2","expected_sequence":2,"answer_text":"reply two","provisional_anchor_refs":[]}).status_code == 200
    verdict = c.post(f"/api/v2/review-rounds/{rid}/verdicts", json={"command_id":"verdict","expected_sequence":1,"verdict_type":"circumstantial","user_reason":"not now","revival_condition":"when measured"})
    assert verdict.status_code == 200
    assert verdict.json()["fragment"]["verdict"]["revival_condition"] == "when measured"
    # Second verdict rejected after durable commit
    assert c.post(f"/api/v2/review-rounds/{rid}/verdicts", json={"command_id":"v2","expected_sequence":2,"verdict_type":"survived","user_reason":"x"}).status_code == 409
    # Replayed from a fresh store over the same Postgres rows
    fresh_store = PostgresNativeEventStore(engine)
    events = fresh_store.read_events(uid)
    assert [e.event_type for e in events] == ["workspace_created", "claim_created", "review_round_started", "challenge_created", "challenge_answered", "challenge_answered", "verdict_confirmed"]
    from cui.research_universe.application import review_round_projection, workspace_projection, universe_home_projection
    frag = review_round_projection(fresh_store, uid, rid)
    assert frag["verdict"]["verdict_type"] == "circumstantial" and frag["verdict"]["revival_condition"] == "when measured"
    assert frag["challenges"][0]["status"] == "resolved_by_verdict"
    assert len(frag["challenges"][0]["answers"]) == 2
    assert workspace_projection(fresh_store, uid, wid)["pending_challenges"] == []
    assert universe_home_projection(fresh_store, uid)["pending_facts"] == []


def test_pg_defer_withdraw_terminal_and_workspace_home(pg_slice3):
    engine, store, uid, c, database = pg_slice3
    wid, cid, rid, chid = _tracer(c, uid)
    assert c.post(f"/api/v2/challenges/{chid}/defer", json={"command_id":"d","expected_sequence":1,"reason":"r","condition":"c"}).status_code == 200
    assert c.post(f"/api/v2/challenges/{chid}/answers", json={"command_id":"a","expected_sequence":2,"answer_text":"x"}).status_code == 409
    fresh = PostgresNativeEventStore(engine)
    from cui.research_universe.application import workspace_projection, universe_home_projection, review_round_projection
    assert chid not in [x["id"] for x in workspace_projection(fresh, uid, wid)["pending_challenges"]]
    assert chid not in [f["id"] for f in universe_home_projection(fresh, uid)["pending_facts"]]
    assert review_round_projection(fresh, uid, rid)["challenges"][0]["status"] == "deferred"
    assert review_round_projection(fresh, uid, rid)["challenges"][0]["defer"] == {"reason": "r", "condition": "c"}
