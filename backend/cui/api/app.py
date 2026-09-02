"""Two explicit app factories keep native production and native testing separate."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, select

from cui.legacy_archive.api.routes import create_router as create_archive_router
from cui.store.event_store import PostgresEventStore
from cui.store.repository import PostgresRepository
from cui.store.schema import libraries
from cui.research_universe.api.routes import LibraryContext, LocalPrincipal, create_router as create_native_router
from cui.research_universe.api.slice1 import create_slice1_router
from cui.research_universe.api.slice2 import create_slice2_router
from cui.research_universe.api.slice3 import create_slice3_router
from cui.research_universe.api.slice4 import create_slice4_router
from cui.research_universe.api.slice5 import create_slice5_router
from cui.research_universe.api.slice6 import create_slice6_router
from cui.research_universe.api.slice7 import create_corpus_search_router
from cui.research_universe.application import Slice1Service
from cui.research_universe.challenge_generator import RealChallengeGenerator, RealEvidenceCandidateGenerator
from cui.llm.client import create_client
from cui.llm.config import load_llm_config
from cui.research_universe.store.event_store import InMemoryNativeEventStore, NativeEventStore, PostgresNativeEventStore, UniverseAlreadyActive
from cui.research_universe.store.sealed_park_store import InMemorySealedParkStore, PostgresSealedParkStore


def _cors(app: FastAPI) -> FastAPI:
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://localhost:3000"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    return app


def _assert_database_at_head(database_url: str) -> None:
    config = Config(os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    engine = create_engine(database_url)
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current != script.get_current_head():
        raise RuntimeError(f"database revision must be {script.get_current_head()}, found {current!r}; run alembic upgrade head")


def _resolve_library_context(engine, supplied: LibraryContext | None) -> LibraryContext:
    """Resolve exactly one persisted Library; only an empty database may provision."""
    with engine.begin() as conn:
        rows = conn.execute(select(libraries.c.id).order_by(libraries.c.id)).scalars().all()
        if not rows:
            library_id = supplied.library_id if supplied else "local-library"
            conn.execute(libraries.insert().values(id=library_id, name="Local Library", created_at=__import__("datetime").datetime.utcnow()))
            return LibraryContext(library_id)
        if len(rows) != 1:
            raise RuntimeError("native application requires exactly one persisted Library; found ambiguity")
        if supplied is not None and supplied.library_id != rows[0]:
            raise RuntimeError("configured Library does not match the sole persisted Library")
        return LibraryContext(rows[0])


def create_native_app(settings: object | None = None, native_store: NativeEventStore | None = None, library_context: LibraryContext | None = None, principal: LocalPrincipal | None = None) -> FastAPI:
    """Production/development factory: PostgreSQL and schema head are mandatory."""
    from dotenv import load_dotenv  # host bootstrap: kernel never loads .env

    load_dotenv()
    database_url = getattr(settings, "database_url", None) if settings else None
    database_url = database_url or os.getenv("CUI_DATABASE_URL")
    if not database_url:
        raise RuntimeError("CUI_DATABASE_URL is required for the native application")
    _assert_database_at_head(database_url)
    if native_store is not None:
        raise RuntimeError("production native application does not accept injected stores")
    engine = create_engine(database_url, pool_pre_ping=True)
    context = _resolve_library_context(engine, library_context)
    store = PostgresNativeEventStore(engine)
    if store.get_active_universe(context.library_id) is None:
        try:
            store.create_active_universe(context.library_id)
        except UniverseAlreadyActive:
            pass
    app = _cors(FastAPI(title="Cui"))
    resolved_principal = principal or LocalPrincipal()
    config = load_llm_config()
    if config is None:
        raise RuntimeError("CUI_LLM_KEY and CUI_LLM_MODEL are required for native Slice 1 challenge generation")
    client = create_client(config)
    challenge_service = Slice1Service(store, resolved_principal.id, RealChallengeGenerator(client, config.model), RealEvidenceCandidateGenerator(client, config.model))
    app.include_router(create_native_router(store, context, resolved_principal), prefix="/api/v2")
    app.include_router(create_slice1_router(challenge_service, store, context, resolved_principal), prefix="/api/v2")
    app.include_router(create_slice2_router(challenge_service, store, PostgresSealedParkStore(engine), context, resolved_principal), prefix="/api/v2")
    app.include_router(create_slice3_router(challenge_service, store, context, resolved_principal), prefix="/api/v2")
    app.include_router(create_slice4_router(challenge_service, store, context, resolved_principal), prefix="/api/v2")
    app.include_router(create_slice5_router(challenge_service, store, context, resolved_principal), prefix="/api/v2")
    app.include_router(create_slice6_router(challenge_service, store, context, resolved_principal), prefix="/api/v2")
    app.include_router(create_corpus_search_router(store, context), prefix="/api/v2")
    app.include_router(create_archive_router(PostgresRepository(engine), PostgresEventStore(engine), context.library_id), prefix="/api/v2")
    return app


def create_native_test_app(native_store: InMemoryNativeEventStore, library_context: LibraryContext | None = None, principal: LocalPrincipal | None = None, challenge_generator=None, evidence_generator=None) -> FastAPI:
    """Explicit in-memory factory; never selected by missing configuration."""
    app = _cors(FastAPI(title="Cui native test"))
    resolved_context = library_context or LibraryContext("default")
    resolved_principal = principal or LocalPrincipal()
    if challenge_generator is None:
        class _UnavailableGenerator:
            def generate(self, **kwargs): raise RuntimeError("test must inject a challenge generator")
        challenge_generator = _UnavailableGenerator()
    if evidence_generator is None:
        class _UnavailableEvidenceGenerator:
            def generate(self, **kwargs): raise RuntimeError("test must inject an evidence candidate generator")
        evidence_generator = _UnavailableEvidenceGenerator()
    service = Slice1Service(native_store, resolved_principal.id, challenge_generator, evidence_generator)
    app.include_router(create_native_router(native_store, resolved_context, resolved_principal), prefix="/api/v2")
    app.include_router(create_slice1_router(service, native_store, resolved_context, resolved_principal), prefix="/api/v2")
    app.include_router(create_slice2_router(service, native_store, InMemorySealedParkStore(), resolved_context, resolved_principal), prefix="/api/v2")
    app.include_router(create_slice3_router(service, native_store, resolved_context, resolved_principal), prefix="/api/v2")
    app.include_router(create_slice4_router(service, native_store, resolved_context, resolved_principal), prefix="/api/v2")
    app.include_router(create_slice5_router(service, native_store, resolved_context, resolved_principal), prefix="/api/v2")
    app.include_router(create_slice6_router(service, native_store, resolved_context, resolved_principal), prefix="/api/v2")
    app.include_router(create_corpus_search_router(native_store, resolved_context), prefix="/api/v2")
    app.include_router(create_archive_router(), prefix="/api/v2")
    return app


def create_app() -> FastAPI:
    """Deployment entry point; the v1 legacy surface was removed in T3."""
    return create_native_app()
