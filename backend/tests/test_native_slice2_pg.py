"""Slice 2 real PostgreSQL sealed-boundary contract; requires CUI_TEST_DATABASE_URL."""
import os
import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from anneal.api.app import create_native_test_app
from anneal.research_universe.api.routes import LibraryContext
from anneal.research_universe.application import ChallengeDraft
from anneal.research_universe.store.event_store import PostgresNativeEventStore, CommandFingerprintConflict
from anneal.research_universe.store.sealed_park_store import PostgresSealedParkStore
from tests.pg_temp_db import temporary_database_url, drop_temporary_database
PG_URL=os.getenv("CUI_TEST_DATABASE_URL")
pytestmark=pytest.mark.skipif(not PG_URL,reason="No PG (set CUI_TEST_DATABASE_URL)")
SENTINEL="PARK-SENTINEL-raw-must-stay-sealed"
class Generator:
 def __init__(self): self.inputs=[]
 def generate(self,*,question,claim): self.inputs.append((question,claim)); return ChallengeDraft("gap","why","check","test",None,[],"low")
from pathlib import Path
from alembic.config import Config

def _alembic_config(url):
 config=Config(str(Path(__file__).parents[1] / "alembic.ini")); config.set_main_option("sqlalchemy.url",url); return config

@pytest.fixture()
def pg(monkeypatch):
 temp_url,database=temporary_database_url(PG_URL)
 monkeypatch.setenv("CUI_DATABASE_URL",temp_url); command.upgrade(_alembic_config(temp_url),"head")
 engine=create_engine(temp_url,pool_pre_ping=True)
 with engine.begin() as x: x.execute(text("TRUNCATE sealed_park_commands, sealed_park_captures, ru_events, ru_commits, ru_streams, research_universes RESTART IDENTITY CASCADE"))
 store=PostgresNativeEventStore(engine); uid=store.create_active_universe("park-pg"); sealed=PostgresSealedParkStore(engine); g=Generator()
 # explicit adapters are intentionally injected into test app's router after factory construction is not available;
 # construct through production-equivalent API router wiring.
 from fastapi import FastAPI
 from anneal.research_universe.api.routes import create_router
 from anneal.research_universe.api.slice1 import create_slice1_router
 from anneal.research_universe.api.slice2 import create_slice2_router
 from anneal.research_universe.application import Slice1Service
 from anneal.research_universe.api.routes import LocalPrincipal
 app=FastAPI(); principal=LocalPrincipal(); service=Slice1Service(store,principal.id,g); ctx=LibraryContext("park-pg")
 app.include_router(create_router(store,ctx,principal),prefix="/api/v2"); app.include_router(create_slice1_router(service,store,ctx,principal),prefix="/api/v2"); app.include_router(create_slice2_router(service,store,sealed,ctx,principal),prefix="/api/v2")
 yield engine,store,sealed,uid,TestClient(app),g,database
 engine.dispose(); drop_temporary_database(PG_URL,database)
def test_pg_sealed_capture_boundary_replay_restart_and_atomic_release(pg):
 engine,store,sealed,uid,c,g,_=pg
 first=c.post("/api/v2/park-captures",json={"command_id":"cap","expected_sequence":0,"original_text":SENTINEL}); assert first.status_code==201
 cid=first.json()["result"]["capture_id"]; assert c.post("/api/v2/park-captures",json={"command_id":"cap","expected_sequence":0,"original_text":SENTINEL}).json()["result"]==first.json()["result"]
 assert c.post("/api/v2/park-captures",json={"command_id":"cap","expected_sequence":0,"original_text":"different"}).status_code==409
 assert sealed.get("park-pg",cid).original_text==SENTINEL and PostgresSealedParkStore(engine).get("park-pg",cid).original_text==SENTINEL
 assert store.read_events(uid)==[]
 listed=c.get("/api/v2/park-captures").json(); assert SENTINEL not in str(listed) and "original_text" not in listed["captures"][0]
 assert c.get(f"/api/v2/park-captures/{cid}").json()["original_text"]==SENTINEL
 created=c.post(f"/api/v2/park-captures/{cid}/release",json={"command_id":"release","expected_sequence":0,"question":"user authored?","provisional_role":"unnamed"}); assert created.status_code==200
 wid=created.json()["result"]["workspace_id"]; events=store.read_events(uid)
 assert len(events)==2 and all(SENTINEL not in str(e.payload) for e in events)
 release=next(e for e in events if e.event_type=="park_released"); assert set(release.payload)=={"release_id","capture_id","workspace_id","provisional_role"}
 assert SENTINEL not in str(c.get(f"/api/v2/universes/{uid}/home").json()) and SENTINEL not in str(c.get(f"/api/v2/workspaces/{wid}").json())
 claim=c.post(f"/api/v2/workspaces/{wid}/claims",json={"command_id":"claim","expected_sequence":0,"text":"authored claim"}).json()["result"]["claim_id"]
 c.post(f"/api/v2/claims/{claim}/review-rounds",json={"command_id":"round","expected_sequence":0}); assert all(SENTINEL not in str(i) for i in g.inputs)
def test_pg_library_isolation_and_active_universe_replacement(pg):
 engine,store,sealed,uid,c,g,_=pg; cid=c.post("/api/v2/park-captures",json={"command_id":"cap2","expected_sequence":0,"original_text":SENTINEL}).json()["result"]["capture_id"]
 # Direct sealed adapter verifies Library boundary. Active universe replacement is represented by archival/new active row.
 with engine.begin() as x: x.execute(text("UPDATE research_universes SET archived_at=NOW() WHERE id=:id"),{"id":uid})
 replacement=store.create_active_universe("park-pg")
 assert c.get("/api/v2/park-captures").json()["captures"][0]["id"]==cid
 foreign=PostgresSealedParkStore(engine); assert foreign.get("other-library",cid) is None
 assert c.post(f"/api/v2/park-captures/{cid}/release",json={"command_id":"r","expected_sequence":0,"workspace_id":"foreign","provisional_role":"unnamed"}).status_code==404


def test_pg_history_aggregates_archived_and_active_universes(pg):
 engine,store,sealed,uid,c,g,_=pg
 cid=c.post("/api/v2/park-captures",json={"command_id":"history-cap","expected_sequence":0,"original_text":SENTINEL}).json()["result"]["capture_id"]
 a=c.post(f"/api/v2/park-captures/{cid}/release",json={"command_id":"history-a","expected_sequence":0,"question":"A question","provisional_role":"unnamed"}).json(); wa=a["result"]["workspace_id"]; ra=a["result"]["release_id"]
 claim=c.post(f"/api/v2/workspaces/{wa}/claims",json={"command_id":"history-claim","expected_sequence":0,"text":"user claim"}).json()["result"]["claim_id"]
 assert c.post(f"/api/v2/workspaces/{wa}/claims/forge-provenance",json={"command_id":"history-forge","expected_sequence":0,"claim_id":claim,"capture_id":cid,"release_id":ra}).status_code==200
 with engine.begin() as x: x.execute(text("UPDATE research_universes SET archived_at=NOW() WHERE id=:id"),{"id":uid})
 b=store.create_active_universe("park-pg")
 assert c.post(f"/api/v2/park-captures/{cid}/release",json={"command_id":"history-b","expected_sequence":0,"question":"B question","provisional_role":"material_lead"}).status_code==200
 history=c.get(f"/api/v2/park-captures/{cid}").json()
 assert {r["universe_id"] for r in history["releases"]}=={uid,b} and {r["universe_id"] for r in history["forged_into"]}=={uid}
 assert history["forged_into"][0]["claim_id"]==claim and all(SENTINEL not in str(e.payload) for u in (uid,b) for e in store.read_events(u))
