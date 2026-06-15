"""Dependency injection for FastAPI.

Module-level state holding store instances.  Provides FastAPI Depends
callables for each service.  Uses a lifespan context manager for setup.
"""

from __future__ import annotations

from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from anneal.services.event_service import EventService
from anneal.services.grill_service import GrillService
from anneal.services.lens_feed_service import (
    InMemoryLensFeedStore,
    LensFeedService,
)
from anneal.services.park_service import ParkService
from anneal.services.promote_service import PromoteService
from anneal.store.event_store import EventStore, InMemoryEventStore


# ---------------------------------------------------------------------------
# Module-level state — populated by the lifespan context manager
# ---------------------------------------------------------------------------

_state: dict[str, object] = {}


def _init_state() -> None:
    """Initialize all stores and services (InMemory for now)."""
    event_store = InMemoryEventStore()
    feed_store = InMemoryLensFeedStore()
    event_service = EventService(event_store)

    _state["event_store"] = event_store
    _state["feed_store"] = feed_store
    _state["event_service"] = event_service
    _state["park_service"] = ParkService(event_store, event_service)
    _state["grill_service"] = GrillService(event_store, event_service)
    _state["promote_service"] = PromoteService(event_store, event_service)
    _state["lens_feed_service"] = LensFeedService(event_store, feed_store)

    # Temporary mapping: library_id -> [artifact_id]
    # Updated when park() is called.  Will be replaced by a proper repository.
    _state["library_artifacts"] = defaultdict(list)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan — initialise stores on startup, teardown on shutdown."""
    _init_state()
    yield
    _state.clear()


# ---------------------------------------------------------------------------
# FastAPI dependency functions
# ---------------------------------------------------------------------------


def get_event_store() -> EventStore:
    return _state["event_store"]  # type: ignore[return-value]


def get_event_service() -> EventService:
    return _state["event_service"]  # type: ignore[return-value]


def get_park_service() -> ParkService:
    return _state["park_service"]  # type: ignore[return-value]


def get_grill_service() -> GrillService:
    return _state["grill_service"]  # type: ignore[return-value]


def get_promote_service() -> PromoteService:
    return _state["promote_service"]  # type: ignore[return-value]


def get_lens_feed_service() -> LensFeedService:
    return _state["lens_feed_service"]  # type: ignore[return-value]


def get_library_artifacts() -> dict[str, list[str]]:
    return _state["library_artifacts"]  # type: ignore[return-value]
