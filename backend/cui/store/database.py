"""Database engine helpers (kernel layer: the host loads .env, never this module)."""

from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine

from cui.store.schema import metadata

DEFAULT_URL = "postgresql://localhost:5432/anneal"


def get_database_url() -> str:
    # Kernel purity: this module never loads dotenv — the host (cui.api.app or
    # the calling script) loads backend/.env before asking for a URL.
    return os.getenv("CUI_DATABASE_URL", DEFAULT_URL)


def create_db_engine(url: str | None = None) -> Engine:
    url = url or get_database_url()
    return create_engine(url, pool_pre_ping=True)


def create_all_tables(engine: Engine) -> None:
    metadata.create_all(engine)
