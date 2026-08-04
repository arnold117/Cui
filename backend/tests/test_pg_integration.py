"""PostgreSQL integration tests.

Skipped when CUI_TEST_DATABASE_URL is not set.
"""

from __future__ import annotations

import os
from uuid import uuid4
from sqlalchemy.engine import make_url
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, inspect, text, select
from alembic import command
from alembic.config import Config
from pathlib import Path
from fastapi.testclient import TestClient

from anneal.domain.events import Event, make_event
from anneal.domain.models import Artifact, Claim, Library, Project, Material
from anneal.services.lens_feed_service import LensFeedEntry, PostgresLensFeedStore
from anneal.store.database import create_all_tables
from anneal.store.event_store import DuplicateEventError, PostgresEventStore
from anneal.store.repository import PostgresRepository
from anneal.store.schema import metadata
from anneal.store.schema import metadata as legacy_metadata
from anneal.store import schema

PG_URL = os.getenv("CUI_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not PG_URL, reason="No PG (set CUI_TEST_DATABASE_URL)")


@pytest.fixture()
def engine():
    """Create engine, create all tables, yield, then drop all tables."""
    eng = create_engine(PG_URL, pool_pre_ping=True)
    create_all_tables(eng)
    yield eng
    metadata.drop_all(eng)
    eng.dispose()


# ------------------------------------------------------------------
# PostgresEventStore
# ------------------------------------------------------------------


class TestPostgresEventStore:
    def test_append_and_get(self, engine) -> None:
        store = PostgresEventStore(engine)
        evt = make_event(type="challenge", actor="grill")
        store.append("art-1", evt)

        events = store.get_events("art-1")
        assert len(events) == 1
        assert events[0].id == evt.id
        assert events[0].type == "challenge"

    def test_duplicate_raises(self, engine) -> None:
        store = PostgresEventStore(engine)
        evt = make_event(type="challenge", actor="grill")
        store.append("art-1", evt)

        with pytest.raises(DuplicateEventError):
            store.append("art-1", evt)

    def test_ordering_by_ts_seq(self, engine) -> None:
        store = PostgresEventStore(engine)
        now = datetime.utcnow()

        # Two events with same timestamp — ordering by seq should preserve insertion order.
        e1 = Event(type="challenge", actor="grill", ts=now)
        e2 = Event(type="answer", actor="user", ts=now)
        # Third event with later timestamp.
        e3 = Event(type="verdict", actor="grill", ts=now + timedelta(seconds=1))

        store.append("art-1", e1)
        store.append("art-1", e2)
        store.append("art-1", e3)

        events = store.get_events("art-1")
        assert len(events) == 3
        assert events[0].id == e1.id
        assert events[1].id == e2.id
        assert events[2].id == e3.id

    def test_get_events_by_type(self, engine) -> None:
        store = PostgresEventStore(engine)
        e1 = make_event(type="challenge", actor="grill")
        e2 = make_event(type="answer", actor="user")
        e3 = make_event(type="challenge", actor="grill")

        store.append("art-1", e1)
        store.append("art-1", e2)
        store.append("art-1", e3)

        challenges = store.get_events_by_type("art-1", "challenge")
        assert len(challenges) == 2
        assert all(e.type == "challenge" for e in challenges)


# ------------------------------------------------------------------
# PostgresRepository
# ------------------------------------------------------------------


class TestPostgresRepository:
    def test_artifact_round_trip(self, engine) -> None:
        repo = PostgresRepository(engine)

        # Create prerequisites.
        lib = Library(id="lib-1", name="Test Lib")
        repo.create_library(lib)
        proj = Project(id="proj-1", library_id="lib-1", goal="Goal")
        repo.create_project(proj)
        mat = Material(id="mat-1", library_id="lib-1", kind="pdf")
        repo.create_material(mat)

        art = Artifact(
            id="art-1",
            library_id="lib-1",
            kind="paper",
            goal="Write paper",
            title="Paper Title",
            project_ids=["proj-1"],
            material_ids=["mat-1"],
        )
        repo.create_artifact(art)

        got = repo.get_artifact("art-1")
        assert got is not None
        assert got.id == "art-1"
        assert got.kind == "paper"
        assert got.goal == "Write paper"
        assert got.title == "Paper Title"
        assert got.project_ids == ["proj-1"]
        assert got.material_ids == ["mat-1"]

    def test_list_artifacts(self, engine) -> None:
        repo = PostgresRepository(engine)

        lib1 = Library(id="lib-1", name="Lib 1")
        lib2 = Library(id="lib-2", name="Lib 2")
        repo.create_library(lib1)
        repo.create_library(lib2)

        a1 = Artifact(id="a1", library_id="lib-1", kind="paper", goal="g1")
        a2 = Artifact(id="a2", library_id="lib-1", kind="paper", goal="g2")
        a3 = Artifact(id="a3", library_id="lib-2", kind="paper", goal="g3")
        repo.create_artifact(a1)
        repo.create_artifact(a2)
        repo.create_artifact(a3)

        lib1_arts = repo.list_artifacts("lib-1")
        assert len(lib1_arts) == 2
        assert {a.id for a in lib1_arts} == {"a1", "a2"}

    def test_get_nonexistent(self, engine) -> None:
        repo = PostgresRepository(engine)
        assert repo.get_artifact("nope") is None
        assert repo.get_library("nope") is None
        assert repo.get_claim("nope") is None

    def test_list_claims(self, engine) -> None:
        repo = PostgresRepository(engine)

        lib1 = Library(id="lib-1", name="Lib 1")
        lib2 = Library(id="lib-2", name="Lib 2")
        repo.create_library(lib1)
        repo.create_library(lib2)

        c1 = Claim(id="c1", library_id="lib-1", body="b1")
        c2 = Claim(id="c2", library_id="lib-1", body="b2")
        c3 = Claim(id="c3", library_id="lib-2", body="b3")
        repo.create_claim(c1)
        repo.create_claim(c2)
        repo.create_claim(c3)

        lib1_claims = repo.list_claims("lib-1")
        assert len(lib1_claims) == 2
        assert {c.id for c in lib1_claims} == {"c1", "c2"}

        lib2_claims = repo.list_claims("lib-2")
        assert {c.id for c in lib2_claims} == {"c3"}


# ------------------------------------------------------------------
# PostgresLensFeedStore
# ------------------------------------------------------------------


class TestPostgresLensFeedStore:
    def test_append_and_list(self, engine) -> None:
        # Need a library row for the FK.
        repo = PostgresRepository(engine)
        repo.create_library(Library(id="lib-1", name="Test Lib"))

        store = PostgresLensFeedStore(engine)
        entry = LensFeedEntry(
            library_id="lib-1",
            artifact_id="art-1",
            event_id="evt-1",
            event_type="challenge",
        )
        store.append(entry)

        entries = store.list_entries("lib-1")
        assert len(entries) == 1
        assert entries[0].id == entry.id
        assert entries[0].event_type == "challenge"

    def test_list_filters_by_library(self, engine) -> None:
        repo = PostgresRepository(engine)
        repo.create_library(Library(id="lib-1", name="Lib 1"))
        repo.create_library(Library(id="lib-2", name="Lib 2"))

        store = PostgresLensFeedStore(engine)
        e1 = LensFeedEntry(library_id="lib-1", artifact_id="a1", event_id="e1", event_type="challenge")
        e2 = LensFeedEntry(library_id="lib-2", artifact_id="a2", event_id="e2", event_type="verdict")
        store.append(e1)
        store.append(e2)

        assert len(store.list_entries("lib-1")) == 1
        assert len(store.list_entries("lib-2")) == 1
        assert store.list_entries("lib-1")[0].library_id == "lib-1"


# ------------------------------------------------------------------
# Native Research Universe Postgres contract (never SQLite proof)
# ------------------------------------------------------------------

from concurrent.futures import ThreadPoolExecutor
from anneal.research_universe.store import schema as native_schema
from anneal.research_universe.store.event_store import ExpectedSequenceConflict, PostgresNativeEventStore
from anneal.research_universe.domain.events import PendingNativeEvent

def _alembic_config(url: str) -> Config:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    return config

@pytest.fixture()
def native_engine(monkeypatch):
    monkeypatch.setenv("CUI_DATABASE_URL", PG_URL)
    command.upgrade(_alembic_config(PG_URL), "head")
    eng = create_engine(PG_URL, pool_pre_ping=True)
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE ru_events, ru_commits, ru_streams, research_universes RESTART IDENTITY CASCADE"))
        conn.execute(text("DELETE FROM libraries"))
        conn.execute(text("INSERT INTO ru_commit_fence (id) VALUES (1) ON CONFLICT (id) DO NOTHING"))
    yield eng
    eng.dispose()

def _workspace_event(aggregate_id: str) -> PendingNativeEvent:
    return PendingNativeEvent(event_type="workspace_created", aggregate_type="workspace", aggregate_id=aggregate_id, payload={"workspace_id": aggregate_id, "initial_question_version_id": f"q-{aggregate_id}", "initial_question_text": "Question?"})

def _append_native(store, universe, command, aggregate):
    return store.append(universe_id=universe, command_id=command, command_type="create_workspace", command_payload={"workspace_id": aggregate}, actor_kind="user", actor_id="local", expected_sequences={("workspace", aggregate): 0}, events=[_workspace_event(aggregate)], result_payload={"workspace_id": aggregate})

def test_native_concurrent_streams_have_unique_global_cursor(native_engine):
    store = PostgresNativeEventStore(native_engine)
    universe = store.create_active_universe("native-library")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda n: _append_native(store, universe, f"command-{n}", f"workspace-{n}"), range(2)))
    assert sorted(x.commit_position for x in results) == [1, 2]
    assert [e.commit_position for e in store.read_events(universe)] == [1, 2]

def test_native_same_command_replays_and_same_stream_conflicts(native_engine):
    store = PostgresNativeEventStore(native_engine)
    universe = store.create_active_universe("native-library")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _append_native(store, universe, "same-command", "workspace"), range(2)))
    assert {x.commit_position for x in results} == {1}
    assert sum(x.replayed for x in results) == 1
    assert len(store.read_events(universe)) == 1

def test_native_command_ids_are_universe_scoped(native_engine):
    store = PostgresNativeEventStore(native_engine)
    first = store.create_active_universe("library-one")
    second = store.create_active_universe("library-two")
    assert _append_native(store, first, "shared-command", "one").replayed is False
    result = _append_native(store, second, "shared-command", "two")
    assert result.replayed is False
    assert len(store.read_events(first)) == len(store.read_events(second)) == 1


def test_native_missing_commit_fence_fails_closed(native_engine):
    store = PostgresNativeEventStore(native_engine)
    universe = store.create_active_universe("native-library")
    with native_engine.begin() as conn:
        conn.execute(native_schema.ru_commit_fence.delete())
    with pytest.raises(RuntimeError, match="commit fence"):
        _append_native(store, universe, "command", "workspace")


def test_native_migration_schema_matches_runtime_metadata(native_engine):
    inspector = inspect(native_engine)
    for table in native_schema.metadata.sorted_tables:
        actual_fks = {(x["name"], tuple(x["constrained_columns"]), x["referred_table"], tuple(x["referred_columns"])) for x in inspector.get_foreign_keys(table.name)}
        expected_fks = {(fk.name, tuple(e.parent.name for e in fk.elements), fk.elements[0].column.table.name, tuple(e.column.name for e in fk.elements)) for fk in table.foreign_key_constraints}
        assert actual_fks == expected_fks

def test_populated_legacy_preflight_stamp_upgrade_preserves_rows():
    from anneal.migrations_preflight_legacy import verify_legacy_schema
    source = make_url(PG_URL)
    database = f"anneal_cutover_{uuid4().hex[:12]}"
    admin = create_engine(str(source.set(database="postgres")), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection: connection.execute(text(f'CREATE DATABASE "{database}"'))
    url = str(source.set(database=database))
    try:
        legacy = create_engine(url)
        legacy_metadata.create_all(legacy)
        with legacy.begin() as conn:
            conn.execute(schema.libraries.insert().values(id="legacy-lib", name="Legacy", created_at=datetime.utcnow()))
            conn.execute(schema.artifacts.insert().values(id="legacy-artifact", library_id="legacy-lib", kind="paper", goal="preserve", created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
        verify_legacy_schema(url)
        previous = os.environ.get("CUI_DATABASE_URL")
        os.environ["CUI_DATABASE_URL"] = url
        try:
            config = _alembic_config(url)
            command.stamp(config, "legacy_baseline")
            command.upgrade(config, "head")
        finally:
            if previous is None: os.environ.pop("CUI_DATABASE_URL", None)
            else: os.environ["CUI_DATABASE_URL"] = previous
        with legacy.connect() as conn:
            assert conn.execute(select(schema.artifacts.c.id).where(schema.artifacts.c.id == "legacy-artifact")).scalar_one() == "legacy-artifact"
            assert "ru_events" in inspect(legacy).get_table_names()
        legacy.dispose()
    finally:
        try: legacy.dispose()
        except UnboundLocalError: pass
        with admin.connect() as connection: connection.execute(text(f'DROP DATABASE IF EXISTS "{database}"'))
        admin.dispose()

def test_native_concurrent_absent_same_stream_returns_replay(native_engine):
    store = PostgresNativeEventStore(native_engine)
    universe = store.create_active_universe("race-library")
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: _append_native(store, universe, "absent-same", "initially-absent"), range(2)))
    assert len({x.commit_position for x in outcomes}) == 1
    assert sum(x.replayed for x in outcomes) == 1

def test_native_production_factory_smoke_on_migrated_database(native_engine, monkeypatch):
    from anneal.api.app import create_native_app
    monkeypatch.setenv("CUI_DATABASE_URL", PG_URL)
    app = create_native_app()
    with TestClient(app) as client:
        active = client.get("/api/v2/universes/active")
        assert active.status_code == 200
        assert active.json()["library_id"]
        assert client.post("/api/v2/universes").json() == active.json()
        assert client.get("/api/v1/artifacts").status_code == 404


def test_native_distinct_commands_racing_new_stream_yield_sequence_conflict(native_engine):
    store = PostgresNativeEventStore(native_engine)
    universe = store.create_active_universe("distinct-race-library")

    def append(command_id: str):
        try:
            return _append_native(store, universe, command_id, "initially-absent")
        except ExpectedSequenceConflict as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(append, ("distinct-race-a", "distinct-race-b")))

    successes = [result for result in outcomes if not isinstance(result, Exception)]
    conflicts = [result for result in outcomes if isinstance(result, ExpectedSequenceConflict)]
    assert len(successes) == 1
    assert successes[0].replayed is False
    assert len(conflicts) == 1
    events = store.read_events(universe)
    assert len(events) == 1
    assert events[0].aggregate_id == "initially-absent"
    with native_engine.connect() as conn:
        assert conn.execute(select(native_schema.ru_commits.c.position)).all() == [(successes[0].commit_position,)]
