"""Lens feed service — writes grilled trajectory into the Lens feed table.

Empty-table hook: no learning algorithm, just persist grilled events for
downstream Lens consumption.

Spec acceptance (§5 line 5):
    "这条完整 trajectory 能被写入 Lens 投喂点
     （哪怕下游只是落库、不学习）。"

Includes both survived AND killed ideas — killed = private mining asset
(spec §2.2). Excludes PARK-only items (assert_park_isolation), surface-scope
edits, and unconfirmed events.

Dependency: EventStore → EventService → LensFeedService.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from sqlalchemy import Engine, insert, select

from cui.domain.events import Event
from cui.domain.invariants import ParkIsolationViolation, assert_park_isolation
from cui.domain.projections import lens_feed_projection
from cui.store.event_store import EventStore
from cui.store import schema


class LensFeedEntry(BaseModel):
    """A record written to the Lens feed table."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    library_id: str
    artifact_id: str
    event_id: str
    event_type: str
    ingested_at: datetime = Field(default_factory=datetime.utcnow)


class LensFeedStore(Protocol):
    """Protocol for Lens feed persistence."""

    def append(self, entry: LensFeedEntry) -> None: ...
    def list_entries(self, library_id: str) -> list[LensFeedEntry]: ...


class InMemoryLensFeedStore:
    """In-memory implementation for tests."""

    def __init__(self) -> None:
        self._entries: list[LensFeedEntry] = []

    def append(self, entry: LensFeedEntry) -> None:
        self._entries.append(entry)

    def list_entries(self, library_id: str) -> list[LensFeedEntry]:
        return [e for e in self._entries if e.library_id == library_id]


class PostgresLensFeedStore:
    """PostgreSQL-backed Lens feed store using SQLAlchemy Core."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def append(self, entry: LensFeedEntry) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                insert(schema.lens_feed_entries).values(
                    id=entry.id,
                    library_id=entry.library_id,
                    artifact_id=entry.artifact_id,
                    event_id=entry.event_id,
                    event_type=entry.event_type,
                    ingested_at=entry.ingested_at,
                )
            )

    def list_entries(self, library_id: str) -> list[LensFeedEntry]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(schema.lens_feed_entries)
                .where(schema.lens_feed_entries.c.library_id == library_id)
                .order_by(schema.lens_feed_entries.c.ingested_at)
            ).fetchall()
        return [
            LensFeedEntry(
                id=row.id,
                library_id=row.library_id,
                artifact_id=row.artifact_id,
                event_id=row.event_id,
                event_type=row.event_type,
                ingested_at=row.ingested_at,
            )
            for row in rows
        ]


class LensFeedService:
    """Service for ingesting grilled trajectories into the Lens feed.

    Uses lens_feed_projection to filter events, then writes each qualifying
    event as a LensFeedEntry into the feed store.
    """

    def __init__(self, event_store: EventStore, feed_store: LensFeedStore) -> None:
        self._event_store = event_store
        self._feed_store = feed_store

    def ingest(self, artifact_id: str, library_id: str) -> list[LensFeedEntry]:
        """Compute lens_feed_projection for the artifact's events and write entries.

        - Calls assert_park_isolation -- parked artifacts cannot be ingested.
        - Includes both survived AND killed ideas (both are Lens food).
        - Excludes surface-scope edits.
        - Excludes unconfirmed events.
        - Returns list of ingested entries.

        Raises ParkIsolationViolation if the artifact is still in PARK.
        """
        events = self._event_store.get_events(artifact_id)

        # PARK = sealed isolation zone; must grill first.
        assert_park_isolation(events)

        # Pure projection: filter to Lens-eligible events.
        feed_events = lens_feed_projection(events)

        entries: list[LensFeedEntry] = []
        for event in feed_events:
            entry = LensFeedEntry(
                library_id=library_id,
                artifact_id=artifact_id,
                event_id=event.id,
                event_type=event.type,
            )
            self._feed_store.append(entry)
            entries.append(entry)

        return entries

    def query_feed(self, library_id: str) -> list[LensFeedEntry]:
        """Return all Lens feed entries for a library."""
        return self._feed_store.list_entries(library_id)
