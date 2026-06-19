"""PostgreSQL integration tests.

Skipped when ANNEAL_TEST_DATABASE_URL is not set.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine

from anneal.domain.events import Event, make_event
from anneal.domain.models import Artifact, Claim, Library, Project, Material
from anneal.services.lens_feed_service import LensFeedEntry, PostgresLensFeedStore
from anneal.store.database import create_all_tables
from anneal.store.event_store import DuplicateEventError, PostgresEventStore
from anneal.store.repository import PostgresRepository
from anneal.store.schema import metadata

PG_URL = os.getenv("ANNEAL_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not PG_URL, reason="No PG (set ANNEAL_TEST_DATABASE_URL)")


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
