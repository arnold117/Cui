from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import pytest

from anneal.domain.events import CHALLENGE, PARK, VERDICT, Event, make_event
from anneal.store.event_store import DuplicateEventError, InMemoryEventStore, SqliteEventStore


@pytest.fixture()
def memory_store() -> InMemoryEventStore:
    return InMemoryEventStore()


@pytest.fixture()
def sqlite_store(tmp_path: Path) -> SqliteEventStore:
    return SqliteEventStore(str(tmp_path / "test.db"))


@pytest.fixture(params=["memory", "sqlite"])
def store(request: pytest.FixtureRequest, memory_store, sqlite_store):
    if request.param == "memory":
        return memory_store
    return sqlite_store


# ── Append + retrieve preserves order ────────────────────────────────


class TestAppendAndRetrieveOrder:
    def test_events_returned_in_timestamp_order(self, store):
        e1 = make_event(type=PARK, actor="user", payload={"seq": 1})
        # Small sleep to guarantee distinct timestamps
        time.sleep(0.01)
        e2 = make_event(type=CHALLENGE, actor="system", payload={"seq": 2})
        time.sleep(0.01)
        e3 = make_event(type=VERDICT, actor="system", payload={"seq": 3})

        store.append("art-1", e1)
        store.append("art-1", e2)
        store.append("art-1", e3)

        events = store.get_events("art-1")
        assert len(events) == 3
        assert events[0].id == e1.id
        assert events[1].id == e2.id
        assert events[2].id == e3.id

    def test_single_event_round_trip(self, store):
        e = make_event(type=PARK, actor="user", payload={"key": "value"})
        store.append("art-1", e)
        events = store.get_events("art-1")
        assert len(events) == 1
        assert events[0].id == e.id
        assert events[0].type == e.type
        assert events[0].actor == e.actor
        assert events[0].payload == e.payload
        assert events[0].debt == e.debt
        assert events[0].confirmed == e.confirmed


# ── Multiple artifacts are isolated ──────────────────────────────────


class TestArtifactIsolation:
    def test_events_for_different_artifacts_are_isolated(self, store):
        e_a = make_event(type=PARK, actor="user", payload={"for": "A"})
        e_b = make_event(type=CHALLENGE, actor="system", payload={"for": "B"})

        store.append("art-A", e_a)
        store.append("art-B", e_b)

        events_a = store.get_events("art-A")
        events_b = store.get_events("art-B")

        assert len(events_a) == 1
        assert events_a[0].id == e_a.id

        assert len(events_b) == 1
        assert events_b[0].id == e_b.id

    def test_get_events_by_type_respects_artifact_boundary(self, store):
        e_a = make_event(type=PARK, actor="user")
        e_b = make_event(type=PARK, actor="user")

        store.append("art-A", e_a)
        store.append("art-B", e_b)

        parks_a = store.get_events_by_type("art-A", PARK)
        assert len(parks_a) == 1
        assert parks_a[0].id == e_a.id


# ── get_events_by_type filters correctly ─────────────────────────────


class TestGetEventsByType:
    def test_filters_to_requested_type(self, store):
        e_park = make_event(type=PARK, actor="user")
        time.sleep(0.01)
        e_challenge = make_event(type=CHALLENGE, actor="system")
        time.sleep(0.01)
        e_verdict = make_event(type=VERDICT, actor="system")

        store.append("art-1", e_park)
        store.append("art-1", e_challenge)
        store.append("art-1", e_verdict)

        challenges = store.get_events_by_type("art-1", CHALLENGE)
        assert len(challenges) == 1
        assert challenges[0].id == e_challenge.id

    def test_returns_empty_for_absent_type(self, store):
        e = make_event(type=PARK, actor="user")
        store.append("art-1", e)
        assert store.get_events_by_type("art-1", VERDICT) == []

    def test_multiple_events_of_same_type(self, store):
        e1 = make_event(type=CHALLENGE, actor="system", payload={"q": "first"})
        time.sleep(0.01)
        e2 = make_event(type=CHALLENGE, actor="system", payload={"q": "second"})

        store.append("art-1", e1)
        store.append("art-1", e2)

        challenges = store.get_events_by_type("art-1", CHALLENGE)
        assert len(challenges) == 2
        assert challenges[0].id == e1.id
        assert challenges[1].id == e2.id


# ── No mutation/deletion API ─────────────────────────────────────────


class TestNoMutationAPI:
    def test_no_update_method(self, store):
        assert not hasattr(store, "update")

    def test_no_delete_method(self, store):
        assert not hasattr(store, "delete")

    def test_no_remove_method(self, store):
        assert not hasattr(store, "remove")

    def test_no_clear_method(self, store):
        assert not hasattr(store, "clear")


# ── Empty artifact returns empty list ────────────────────────────────


class TestEmptyArtifact:
    def test_get_events_returns_empty_list(self, store):
        assert store.get_events("nonexistent") == []

    def test_get_events_by_type_returns_empty_list(self, store):
        assert store.get_events_by_type("nonexistent", PARK) == []


# ── Multiple events same artifact in timestamp order ─────────────────


class TestTimestampOrdering:
    def test_many_events_ordered_by_timestamp(self, store):
        events = []
        for i in range(5):
            e = make_event(type=PARK, actor="user", payload={"i": i})
            events.append(e)
            store.append("art-1", e)
            time.sleep(0.01)

        retrieved = store.get_events("art-1")
        assert len(retrieved) == 5
        for i, e in enumerate(retrieved):
            assert e.payload["i"] == i

        # Verify monotonically increasing timestamps
        for i in range(len(retrieved) - 1):
            assert retrieved[i].ts <= retrieved[i + 1].ts


# ── Same-timestamp ordering stability (Fix 3) ──────────────────────────


class TestSameTimestampOrdering:
    def test_insertion_order_preserved_for_same_timestamp(self, store):
        """Two events with the exact same timestamp preserve insertion order."""
        fixed_ts = datetime(2026, 1, 1, 12, 0, 0)
        e1 = Event(type=PARK, actor="user", ts=fixed_ts, payload={"order": 1})
        e2 = Event(type=CHALLENGE, actor="system", ts=fixed_ts, payload={"order": 2})

        store.append("art-1", e1)
        store.append("art-1", e2)

        retrieved = store.get_events("art-1")
        assert len(retrieved) == 2
        assert retrieved[0].id == e1.id
        assert retrieved[1].id == e2.id

    def test_many_same_timestamp_events_stable(self, store):
        """Many events at the same timestamp maintain insertion order."""
        fixed_ts = datetime(2026, 6, 15, 0, 0, 0)
        events = [
            Event(type=PARK, actor="user", ts=fixed_ts, payload={"i": i})
            for i in range(10)
        ]
        for e in events:
            store.append("art-1", e)

        retrieved = store.get_events("art-1")
        assert len(retrieved) == 10
        for i, e in enumerate(retrieved):
            assert e.payload["i"] == i


# ── Duplicate event ID (Fix 2) ─────────────────────────────────────────


class TestDuplicateEventId:
    def test_duplicate_event_id_raises_in_memory(self, memory_store):
        """InMemoryEventStore raises DuplicateEventError on duplicate ID."""
        e = make_event(type=PARK, actor="user")
        memory_store.append("art-1", e)
        with pytest.raises(DuplicateEventError):
            memory_store.append("art-1", e)

    def test_duplicate_event_id_raises_in_sqlite(self, sqlite_store):
        """SqliteEventStore raises DuplicateEventError on duplicate ID."""
        e = make_event(type=PARK, actor="user")
        sqlite_store.append("art-1", e)
        with pytest.raises(DuplicateEventError):
            sqlite_store.append("art-1", e)

    def test_duplicate_across_artifacts_raises(self, store):
        """Duplicate event ID raises even across different artifact IDs."""
        e = make_event(type=PARK, actor="user")
        store.append("art-1", e)
        with pytest.raises(DuplicateEventError):
            store.append("art-2", e)


# ── SqliteEventStore WAL + close + context manager (Fix 1) ─────────────


class TestSqliteWalAndLifecycle:
    def test_wal_mode_enabled(self, tmp_path):
        """SqliteEventStore enables WAL journal mode."""
        store = SqliteEventStore(str(tmp_path / "wal.db"))
        cursor = store._conn.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode == "wal"
        store.close()

    def test_close_method(self, tmp_path):
        """close() makes further operations fail."""
        store = SqliteEventStore(str(tmp_path / "close.db"))
        store.close()
        with pytest.raises(Exception):
            store.append("art-1", make_event(type=PARK, actor="user"))

    def test_context_manager(self, tmp_path):
        """SqliteEventStore works as a context manager."""
        db_path = str(tmp_path / "ctx.db")
        with SqliteEventStore(db_path) as store:
            e = make_event(type=PARK, actor="user")
            store.append("art-1", e)
            events = store.get_events("art-1")
            assert len(events) == 1
        # After exiting, the connection should be closed.
        with pytest.raises(Exception):
            store.append("art-1", make_event(type=PARK, actor="user"))
