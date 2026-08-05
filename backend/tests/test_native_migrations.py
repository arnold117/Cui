import os
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
import pytest

from anneal.migrations_preflight_legacy import verify_legacy_schema
from anneal.store.schema import metadata as legacy_metadata


def _config(url: str) -> Config:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    os.environ["CUI_DATABASE_URL"] = url
    return config


def test_fresh_upgrade_and_native_only_downgrade(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    monkeypatch.setenv("CUI_DATABASE_URL", url)
    config = _config(url)
    command.upgrade(config, "head")
    engine = sa.create_engine(url)
    assert {"research_universes", "ru_streams", "ru_commits", "ru_events", "sealed_park_captures", "sealed_park_commands"} <= set(sa.inspect(engine).get_table_names())
    command.downgrade(config, "native_v1")
    names = set(sa.inspect(engine).get_table_names())
    assert "libraries" in names and "research_universes" in names
    assert not {"sealed_park_captures", "sealed_park_commands"} & names
    command.downgrade(config, "legacy_baseline")
    names = set(sa.inspect(engine).get_table_names())
    assert "libraries" in names
    assert not {"research_universes", "ru_streams", "ru_commits", "ru_events"} & names


def test_preflight_allows_exact_legacy_and_rejects_drift(tmp_path):
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    engine = sa.create_engine(url)
    legacy_metadata.create_all(engine)
    verify_legacy_schema(url)
    with engine.begin() as conn:
        conn.execute(sa.text("DROP TABLE projects"))
    with pytest.raises(RuntimeError, match="mismatch"):
        verify_legacy_schema(url)
