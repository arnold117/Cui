"""Database engine helpers for Anneal."""

from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine

from anneal.store.schema import metadata

DEFAULT_URL = "postgresql://localhost:5432/anneal"


def get_database_url() -> str:
    from dotenv import load_dotenv

    load_dotenv()
    return os.getenv("ANNEAL_DATABASE_URL", DEFAULT_URL)


def create_db_engine(url: str | None = None) -> Engine:
    url = url or get_database_url()
    return create_engine(url, pool_pre_ping=True)


def create_all_tables(engine: Engine) -> None:
    metadata.create_all(engine)
