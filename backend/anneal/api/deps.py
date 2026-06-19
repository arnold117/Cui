"""Dependency injection for FastAPI.

Module-level state holding store instances.  Provides FastAPI Depends
callables for each service.  Uses a lifespan context manager for setup.

When ``ANNEAL_DATABASE_URL`` is set, uses PostgreSQL-backed stores and
repository.  Otherwise falls back to in-memory implementations (tests).
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from anneal.domain.models import Library
from anneal.llm.client import create_client
from anneal.llm.config import load_llm_config
from anneal.services.collect_service import CollectService
from anneal.services.event_service import EventService
from anneal.services.grill_service import GrillService
from anneal.services.grounding_service import GroundingService
from anneal.services.lens_service import LensService
from anneal.services.lens_feed_service import (
    InMemoryLensFeedStore,
    LensFeedService,
    PostgresLensFeedStore,
)
from anneal.services.park_service import ParkService
from anneal.services.promote_service import PromoteService
from anneal.store.database import create_db_engine, create_all_tables
from anneal.store.event_store import (
    EventStore,
    InMemoryEventStore,
    PostgresEventStore,
)
from anneal.store.repository import (
    InMemoryRepository,
    PostgresRepository,
    Repository,
)


# ---------------------------------------------------------------------------
# Module-level state — populated by the lifespan context manager
# ---------------------------------------------------------------------------

_state: dict[str, object] = {}


def _init_state() -> None:
    """Initialize all stores and services.

    If ``ANNEAL_DATABASE_URL`` is set, use PostgreSQL-backed stores.
    Otherwise fall back to in-memory implementations (suitable for tests).
    """
    db_url = os.getenv("ANNEAL_DATABASE_URL")

    if db_url:
        engine = create_db_engine(db_url)
        create_all_tables(engine)
        event_store: EventStore = PostgresEventStore(engine)
        feed_store = PostgresLensFeedStore(engine)
        repo: Repository = PostgresRepository(engine)
    else:
        event_store = InMemoryEventStore()
        feed_store = InMemoryLensFeedStore()
        repo = InMemoryRepository()

    # Ensure default library exists (idempotent — safe on every startup)
    if repo.get_library("default") is None:
        repo.create_library(Library(id="default", name="Default Library"))

    event_service = EventService(event_store)

    llm_config = load_llm_config()
    llm_client = None
    if llm_config:
        try:
            llm_client = create_client(llm_config)
        except ImportError:
            pass  # LLM SDK not installed — auto-grill endpoints return 501

    _state["event_store"] = event_store
    _state["feed_store"] = feed_store
    _state["repository"] = repo
    _state["event_service"] = event_service
    _state["park_service"] = ParkService(event_store, event_service, repo=repo)
    _state["collect_service"] = CollectService(event_store, event_service, repo=repo)
    _state["grill_service"] = GrillService(event_store, event_service, llm=llm_client)
    _state["grounding_service"] = GroundingService(
        event_store, event_service, repo=repo, llm=llm_client
    )
    _state["promote_service"] = PromoteService(event_store, event_service)
    _state["lens_feed_service"] = LensFeedService(event_store, feed_store)
    _state["lens_service"] = LensService(
        event_store, event_service, repo=repo, llm=llm_client
    )


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


def get_collect_service() -> CollectService:
    return _state["collect_service"]  # type: ignore[return-value]


def get_grill_service() -> GrillService:
    return _state["grill_service"]  # type: ignore[return-value]


def get_grounding_service() -> GroundingService:
    return _state["grounding_service"]  # type: ignore[return-value]


def get_promote_service() -> PromoteService:
    return _state["promote_service"]  # type: ignore[return-value]


def get_lens_feed_service() -> LensFeedService:
    return _state["lens_feed_service"]  # type: ignore[return-value]


def get_lens_service() -> LensService:
    return _state["lens_service"]  # type: ignore[return-value]


def get_repository() -> Repository:
    return _state["repository"]  # type: ignore[return-value]
