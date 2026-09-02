"""Dependency injection for FastAPI.

Module-level state holding store instances.  Provides FastAPI Depends
callables for each service.  Uses a lifespan context manager for setup.

When ``CUI_DATABASE_URL`` is set, uses PostgreSQL-backed stores and
repository.  Otherwise falls back to in-memory implementations (tests).
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI

from cui.domain.models import Library
from cui.llm.client import create_client
from cui.llm.config import load_llm_config
from cui.services.collect_service import CollectService
from cui.services.event_service import EventService
from cui.services.grill_service import GrillService
from cui.services.grounding_service import GroundingService
from cui.services.lens_service import LensService
from cui.services.lens_feed_service import (
    InMemoryLensFeedStore,
    LensFeedService,
    PostgresLensFeedStore,
)
from cui.services.park_service import ParkService
from cui.services.promote_service import PromoteService
from cui.store.database import create_db_engine, create_all_tables
from cui.store.event_store import (
    EventStore,
    InMemoryEventStore,
    PostgresEventStore,
)
from cui.store.repository import (
    InMemoryRepository,
    PostgresRepository,
    Repository,
)


# ---------------------------------------------------------------------------
# Module-level state — populated by the lifespan context manager
# ---------------------------------------------------------------------------

_log = logging.getLogger(__name__)


def _storage_logger() -> logging.Logger:
    """Logger the storage banner is actually visible through.

    Resolved at call time, not import time. Under uvicorn the root logger keeps
    its default WARNING level, so an INFO on a plain module logger is silently
    dropped — meaning the "PostgreSQL, you are safe" half of the banner would
    never be seen and only the alarm half would work. ``uvicorn.error`` is the
    logger that owns the running server's handlers. Outside uvicorn (tests,
    scripts) it has none, and we fall back to the module logger.
    """
    uvicorn_log = logging.getLogger("uvicorn.error")
    # NOTE ``hasHandlers()``, not ``.handlers``: uvicorn attaches its handler to
    # the parent "uvicorn" logger and lets "uvicorn.error" propagate, so the
    # child's own handler list is empty even under a live server.
    return uvicorn_log if uvicorn_log.hasHandlers() else _log


_state: dict[str, object] = {}


def _init_state() -> None:
    """Initialize all stores and services.

    If ``CUI_DATABASE_URL`` is set, use PostgreSQL-backed stores.
    Otherwise fall back to in-memory implementations (suitable for tests).

    ``load_dotenv()`` MUST run before that variable is read. It used to be
    reached only later, inside ``load_llm_config()`` — so a ``.env`` supplied
    the LLM key (read after) but never the database URL (read here), and the
    app silently ran on in-memory storage while looking completely healthy:
    grilling worked, and every trajectory it produced died at the next
    restart. 轨迹是护城河 — losing it silently is the worst failure this
    process can have, so the load order is load-bearing, not cosmetic.
    """
    load_dotenv()
    log = _storage_logger()
    db_url = os.getenv("CUI_DATABASE_URL")

    if db_url:
        engine = create_db_engine(db_url)
        create_all_tables(engine)
        event_store: EventStore = PostgresEventStore(engine)
        feed_store = PostgresLensFeedStore(engine)
        repo: Repository = PostgresRepository(engine)
        log.info("event store: PostgreSQL — trajectories persist across restarts")
    else:
        event_store = InMemoryEventStore()
        feed_store = InMemoryLensFeedStore()
        repo = InMemoryRepository()
        # A silent in-memory store is indistinguishable from a persistent one
        # that happens to be empty — the same trap the L3 canary exists for.
        # Say it out loud: this mode DESTROYS every trajectory on shutdown.
        log.warning(
            "event store: IN-MEMORY — CUI_DATABASE_URL is unset, so every "
            "claim, grill and verdict in this session is LOST on shutdown. "
            "Set it in backend/.env (or the environment) to persist. "
            "轨迹是护城河，这个模式下它不会留下来。"
        )

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
    # repo powers 判例先验 — auto_challenge needs the Library scope to collect
    # the researcher's own kill precedents (auto_verdict never sees them).
    _state["grill_service"] = GrillService(
        event_store, event_service, llm=llm_client, repo=repo
    )
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
