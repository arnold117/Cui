"""Slice 5 real PostgreSQL crystallization / direction contract; requires CUI_TEST_DATABASE_URL."""
import os
import pytest
from alembic import command
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from anneal.research_universe.api.routes import LibraryContext, LocalPrincipal, create_router
from anneal.research_universe.api.slice1 import create_slice1_router
from anneal.research_universe.api.slice2 import create_slice2_router
from anneal.research_universe.api.slice3 import create_slice3_router
from anneal.research_universe.api.slice4 import create_slice4_router
from anneal.research_universe.api.slice5 import create_slice5_router
from anneal.research_universe.application import ChallengeDraft, Slice1Service, direction_projection, workspace_projection, universe_home_projection
from anneal.research_universe.store.event_store import PostgresNativeEventStore
from anneal.research_universe.store.sealed_park_store import PostgresSealedParkStore
from tests.pg_temp_db import temporary_database_url, drop_temporary_database
from pathlib import Path
from alembic.config import Config

PG_URL = os.getenv("CUI_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="No PG (set CUI_TEST_DATABASE_URL)")

class Generator:
    def generate(self, *, question, claim):
        return ChallengeDraft("causal gap", "why it matters", "seek a counterexample", "pg-fake-v5", "pg-fake", ["question", "claim"], "moderate")


def _alembic_config(url):
    config = Config(str(Path(__file__).parents[1] / "alembic.ini")); config.set_main_option("sqlalchemy.url", url); return config


@pytest.fixture()
def pg_slice5(monkeypatch):
    temp_url, database = temporary_database_url(PG_URL)
    monkeypatch.setenv("CUI_DATABASE_URL", temp_url); command.upgrade(_alembic_config(temp_url), "head")
    engine = create_engine(temp_url, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE sealed_park_commands, sealed_park_captures, ru_events, ru_commits, ru_streams, research_universes RESTART IDENTITY CASCADE"))
    store = PostgresNativeEventStore(engine); uid = store.create_active_universe("slice5-pg")
    principal = LocalPrincipal(); service = Slice1Service(store, principal.id, Generator()); ctx = LibraryContext("slice5-pg")
    app = FastAPI()
    app.include_router(create_router(store, ctx, principal), prefix="/api/v2")
    app.include_router(create_slice1_router(service, store, ctx, principal), prefix="/api/v2")
    app.include_router(create_slice2_router(service, store, PostgresSealedParkStore(engine), ctx, principal), prefix="/api/v2")
    app.include_router(create_slice3_router(service, store, ctx, principal), prefix="/api/v2")
    app.include_router(create_slice4_router(service, store, ctx, principal), prefix="/api/v2")
    app.include_router(create_slice5_router(service, store, ctx, principal), prefix="/api/v2")
    yield engine, store, uid, TestClient(app), database
    engine.dispose(); drop_temporary_database(PG_URL, database)


def _seq(c, wid):
    return c.get(f"/api/v2/workspaces/{wid}").json()["sequence"]


def test_pg_crystallization_branch_direction_rephrase_persist_and_replay(pg_slice5):
    engine, store, uid, c, database = pg_slice5
    wid = c.post(f"/api/v2/universes/{uid}/workspaces", json={"command_id": "w", "expected_sequence": 0, "question": "Does X cause Y?"}).json()["result"]["workspace_id"]
    # conclude the workspace (user-authored conclusion, deferred requires revival condition)
    conc = c.post(f"/api/v2/workspaces/{wid}/conclusions", json={"command_id": "conc", "expected_sequence": _seq(c, wid), "conclusion_type": "deferred", "conclusion_text": "Pending more data.", "revival_condition": "when Paper A is readable"})
    assert conc.status_code == 200
    conclusion_id = conc.json()["result"]["conclusion_id"]
    # branch atomically creates successor + records source
    branch = c.post(f"/api/v2/workspaces/{wid}/branch", json={"command_id": "br", "expected_sequence": _seq(c, wid), "new_question": "Successor question?", "user_reason": "split"})
    assert branch.status_code == 200
    successor_id = branch.json()["result"]["successor_workspace_id"]
    # create direction, attach, crystallize, rephrase, declare status
    did = c.post(f"/api/v2/universes/{uid}/directions", json={"command_id": "d", "expected_sequence": 0, "proposition": "A long-term thesis."}).json()["result"]["direction_id"]
    link = c.post(f"/api/v2/workspaces/{successor_id}/direction-links", json={"command_id": "link", "expected_sequence": 0, "direction_id": did})
    assert link.status_code == 201
    # crystallize the source conclusion into the direction (workspace has that conclusion)
    cr = c.post(f"/api/v2/directions/{did}/crystallizations", json={"command_id": "x", "expected_sequence": 0, "workspace_id": wid, "conclusion_id": conclusion_id})
    assert cr.status_code == 201
    xid = cr.json()["result"]["crystallization_id"]
    rp = c.post(f"/api/v2/directions/{did}/rephrasings", json={"command_id": "rp", "expected_sequence": 1, "new_proposition": "A narrower thesis.", "change_type": "narrow_or_widen", "user_reason": "after crystallizing", "source_conclusion_ref": conclusion_id})
    assert rp.status_code == 200
    st = c.post(f"/api/v2/directions/{did}/status-declarations", json={"command_id": "st", "expected_sequence": 2, "status": "active", "user_reason": "keep it live"})
    assert st.status_code == 200
    # replay from a fresh store over the same Postgres rows
    fresh = PostgresNativeEventStore(engine)
    events = fresh.read_events(uid)
    types = [e.event_type for e in events]
    assert "workspace_concluded" in types and "workspace_branched" in types and "workspace_created" in types
    assert "direction_created" in types and "workspace_direction_attached" in types
    assert "workspace_crystallization_attached" in types and "direction_proposition_rephrased" in types
    ws = workspace_projection(fresh, uid, wid)
    assert ws["user_position"] == "branched" and ws["successor_workspace_id"] == successor_id
    assert ws["conclusion"]["id"] == conclusion_id and ws["conclusion"]["type"] == "deferred"
    assert ws["conclusion"]["revival_condition"] == "when Paper A is readable"
    succ = workspace_projection(fresh, uid, successor_id)
    assert succ["user_position"] == "exploring" and succ["direction_links"][0]["direction_id"] == did
    dp = direction_projection(fresh, uid, did)
    assert dp["proposition"]["text"] == "A narrower thesis." and dp["status"] == "active"
    assert dp["crystallizations"][0]["crystallization_id"] == xid
    assert dp["crystallizations"][0]["conclusion_id"] == conclusion_id
    assert dp["rephrase_history"][0]["prior_proposition_text"] == "A long-term thesis."
    assert dp["rephrase_history"][0]["source_conclusion_ref"] == conclusion_id
    assert dp["attached_workspaces"][0]["workspace_id"] == successor_id
    home = universe_home_projection(fresh, uid)
    assert home["directions"][0]["id"] == did and home["directions"][0]["crystallizations_count"] == 1
    assert home["directions"][0]["crystallizations"][0]["conclusion_text"] == "Pending more data."


def test_pg_pending_challenge_never_blocks_conclusion(pg_slice5):
    engine, store, uid, c, database = pg_slice5
    wid = c.post(f"/api/v2/universes/{uid}/workspaces", json={"command_id": "w", "expected_sequence": 0, "question": "Does X cause Y?"}).json()["result"]["workspace_id"]
    claim_id = c.post(f"/api/v2/workspaces/{wid}/claims", json={"command_id": "claim", "expected_sequence": 0, "text": "X causes Y."}).json()["result"]["claim_id"]
    rid = c.post(f"/api/v2/claims/{claim_id}/review-rounds", json={"command_id": "round", "expected_sequence": 0}).json()["result"]["review_round_id"]
    assert len(c.get(f"/api/v2/workspaces/{wid}").json()["pending_challenges"]) == 1
    conc = c.post(f"/api/v2/workspaces/{wid}/conclusions", json={"command_id": "conc", "expected_sequence": _seq(c, wid), "conclusion_type": "tentative_answer", "conclusion_text": "X is the cause."})
    assert conc.status_code == 200
    fresh = PostgresNativeEventStore(engine)
    ws = workspace_projection(fresh, uid, wid)
    assert ws["user_position"] == "concluded" and len(ws["pending_challenges"]) == 1
