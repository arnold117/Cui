"""Safe disposable PostgreSQL database helpers for integration tests."""
from __future__ import annotations
from uuid import uuid4
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

_PREFIX = "cui_slice2_"
_FORBIDDEN = {"postgres", "template0", "template1", "anneal", "cui"}

def temporary_database_url(admin_url: str, database: str | None = None) -> tuple[str, str]:
    """Create a uniquely named Slice 2 database; never operate on caller's DB."""
    database = database or f"{_PREFIX}{uuid4().hex}"
    if database in _FORBIDDEN or not database.startswith(_PREFIX):
        raise ValueError("temporary database name must use the generated cui_slice2_ prefix")
    source = make_url(admin_url)
    admin = create_engine(str(source.set(database="postgres")), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{database}"'))
    finally:
        admin.dispose()
    return str(source.set(database=database)), database

def drop_temporary_database(admin_url: str, database: str) -> None:
    if database in _FORBIDDEN or not database.startswith(_PREFIX):
        raise ValueError("refusing to drop a non-generated database")
    source = make_url(admin_url)
    admin = create_engine(str(source.set(database="postgres")), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
    finally:
        admin.dispose()
