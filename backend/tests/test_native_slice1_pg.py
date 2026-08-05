"""Slice 1 PostgreSQL tracer contract; requires CUI_TEST_DATABASE_URL."""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from alembic import command
from concurrent.futures import ThreadPoolExecutor

from anneal.research_universe.api.routes import LibraryContext
from anneal.api.app import create_native_test_app
from anneal.research_universe.application import ChallengeDraft
from anneal.research_universe.store.event_store import PostgresNativeEventStore
from anneal.research_universe.store import schema
from tests.test_pg_integration import _alembic_config

PG_URL = os.getenv("CUI_TEST_DATABASE_URL")

# This test TRUNCATEs native tables + runs alembic directly on the URL's
# database (it does NOT use the guarded pg_temp_db helper). Refuse to run
# against the app DB or any cluster database so an accidental
# CUI_TEST_DATABASE_URL=.../anneal can never wipe real data again.
_FORBIDDEN_DB = frozenset({"postgres", "template0", "template1", "anneal", "cui"})

if PG_URL:
    _target_db = (make_url(PG_URL).database or "").strip()
    if _target_db in _FORBIDDEN_DB or _target_db.startswith("template"):
        raise RuntimeError(f"refusing destructive PG test against database {_target_db!r}; use a disposable database")

pytestmark = pytest.mark.skipif(not PG_URL, reason="No PG (set CUI_TEST_DATABASE_URL)")

class CountingGenerator:
    def __init__(self, fail=False): self.calls=0; self.fail=fail
    def generate(self, *, question, claim):
        self.calls += 1
        if self.fail: raise RuntimeError("generator unavailable")
        return ChallengeDraft("causal identification gap", "the stated evidence may only be correlational", "seek a plausible confounder or counterexample", "pg-fake-v1", "pg-fake", ["review_round.question_snapshot", "review_round.claim_snapshot"], "moderate")

@pytest.fixture()
def pg_slice1(monkeypatch):
    # Alembic env.py intentionally reads only CUI_DATABASE_URL; tests accept
    # the separate test URL and temporarily bridge it for migration execution.
    monkeypatch.setenv("CUI_DATABASE_URL", PG_URL)
    command.upgrade(_alembic_config(PG_URL), "head")
    engine=create_engine(PG_URL, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE ru_events, ru_commits, ru_streams, research_universes RESTART IDENTITY CASCADE"))
    store=PostgresNativeEventStore(engine); universe=store.create_active_universe("slice1-pg-library")
    generator=CountingGenerator()
    # Test factory is explicitly DI-only; it still exercises actual Postgres native store/API/application.
    client=TestClient(create_native_test_app(store, LibraryContext("slice1-pg-library"), challenge_generator=generator))
    yield store, universe, client, generator
    engine.dispose()

def _tracer(store, universe, client):
    wid=client.post(f"/api/v2/universes/{universe}/workspaces",json={"command_id":"workspace","expected_sequence":0,"question":"Does urban tree cover reduce summer heat?"}).json()["result"]["workspace_id"]
    note=client.post(f"/api/v2/workspaces/{wid}/notes",json={"command_id":"note","expected_sequence":1,"text":"Satellite correlations are strongest in dense districts."}).json()["result"]
    assert client.post(f"/api/v2/workspaces/{wid}/anchors",json={"command_id":"anchor","expected_sequence":2,"note_id":note["note_id"],"note_revision_id":note["note_revision_id"],"start":0,"end":9,"selected_text":"Satellite"}).status_code==200
    cid=client.post(f"/api/v2/workspaces/{wid}/claims",json={"command_id":"claim","expected_sequence":0,"text":"Increasing tree cover reduces peak summer heat."}).json()["result"]["claim_id"]
    return wid,cid

def test_pg_slice1_full_tracer_replay_snapshots_and_shared_fact(pg_slice1):
    store,uid,c,g=pg_slice1; wid,cid=_tracer(store,uid,c)
    first=c.post(f"/api/v2/claims/{cid}/review-rounds",json={"command_id":"round","expected_sequence":0}); assert first.status_code==201
    second=c.post(f"/api/v2/claims/{cid}/review-rounds",json={"command_id":"round","expected_sequence":0}); assert second.status_code==201
    assert first.json()["result"]==second.json()["result"] and g.calls==1
    rid=first.json()["result"]["review_round_id"]; challenge_id=first.json()["result"]["challenge_id"]
    workspace=c.get(f"/api/v2/workspaces/{wid}").json(); home=c.get(f"/api/v2/universes/{uid}/home").json(); round_read=c.get(f"/api/v2/review-rounds/{rid}").json()
    assert workspace["pending_challenges"][0]["id"]==home["pending_facts"][0]["id"]==challenge_id
    assert round_read["question_snapshot"]["text"]=="Does urban tree cover reduce summer heat?"
    assert round_read["claim_snapshot"]["text"]=="Increasing tree cover reduces peak summer heat."
    assert workspace["anchors"][0]["note_revision_id"]
    assert c.post(f"/api/v2/claims/{cid}/review-rounds",json={"command_id":"stale","expected_sequence":1}).status_code==409

def test_pg_slice1_concurrent_same_round_generates_once(pg_slice1):
    store,uid,c,g=pg_slice1; _,cid=_tracer(store,uid,c)
    def send(_): return c.post(f"/api/v2/claims/{cid}/review-rounds",json={"command_id":"concurrent-round","expected_sequence":0})
    with ThreadPoolExecutor(max_workers=2) as pool: responses=list(pool.map(send, range(2)))
    assert all(r.status_code == 201 for r in responses)
    assert responses[0].json()["result"] == responses[1].json()["result"] and g.calls == 1


def test_pg_slice1_independent_workers_generate_once(pg_slice1):
    store,uid,c,_=pg_slice1; _,cid=_tracer(store,uid,c)
    # Two stores/services simulate separate workers: only the DB session advisory guard is shared.
    from anneal.research_universe.application import Slice1Service
    from sqlalchemy import create_engine
    g1,g2=CountingGenerator(),CountingGenerator()
    s1=Slice1Service(PostgresNativeEventStore(create_engine(PG_URL)), "worker-1", g1)
    s2=Slice1Service(PostgresNativeEventStore(create_engine(PG_URL)), "worker-2", g2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda service: service.start_review_round(uid,cid,"independent-workers",0), (s1,s2)))
    assert results[0].result_payload == results[1].result_payload
    assert g1.calls + g2.calls == 1


def test_pg_slice1_cross_universe_and_generator_failure_are_atomic(pg_slice1):
    store,uid,c,g=pg_slice1; wid,cid=_tracer(store,uid,c)
    other=store.create_active_universe("other-library")
    assert c.post(f"/api/v2/universes/{other}/workspaces",json={"command_id":"foreign","expected_sequence":0,"question":"no"}).status_code==404
    failing=CountingGenerator(fail=True)
    bad=TestClient(create_native_test_app(store, LibraryContext("slice1-pg-library"), challenge_generator=failing))
    before=len(store.read_events(uid)); response=bad.post(f"/api/v2/claims/{cid}/review-rounds",json={"command_id":"broken-round","expected_sequence":0})
    assert response.status_code==502 and len(store.read_events(uid))==before and failing.calls==1
