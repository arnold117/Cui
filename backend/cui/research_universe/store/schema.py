"""Native Research Universe SQLAlchemy tables; intentionally separate from legacy schema."""

from __future__ import annotations

import sqlalchemy as sa

metadata = sa.MetaData()

research_universes = sa.Table(
    "research_universes", metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("library_id", sa.Text, nullable=False),
    sa.Column("model_generation", sa.Text, nullable=False, server_default="research_universe_v1"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("archived_at", sa.DateTime(timezone=True)),
    sa.Index("uq_active_research_universe_per_library", "library_id", unique=True, postgresql_where=sa.text("archived_at IS NULL")),
)

ru_streams = sa.Table(
    "ru_streams", metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("universe_id", sa.Text, nullable=False),
    sa.Column("aggregate_type", sa.Text, nullable=False),
    sa.Column("aggregate_id", sa.Text, nullable=False),
    sa.Column("next_sequence", sa.BigInteger, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("id", "universe_id", name="uq_ru_stream_id_universe"),
    sa.ForeignKeyConstraint(["universe_id"], ["research_universes.id"], name="fk_ru_stream_universe"),
    sa.UniqueConstraint("universe_id", "aggregate_type", "aggregate_id", name="uq_ru_stream_address"),
)

ru_commit_fence = sa.Table(
    "ru_commit_fence", metadata,
    sa.Column("id", sa.SmallInteger, primary_key=True),
    sa.CheckConstraint("id = 1", name="ck_ru_commit_fence_singleton"),
)

ru_commits = sa.Table(
    "ru_commits", metadata,
    sa.Column("position", sa.BigInteger, primary_key=True, autoincrement=True),
    sa.Column("id", sa.Text, nullable=False, unique=True),
    sa.Column("universe_id", sa.Text, nullable=False),
    sa.Column("command_id", sa.Text, nullable=False),
    sa.Column("command_fingerprint", sa.Text, nullable=False),
    sa.Column("result_payload", sa.JSON, nullable=False),
    sa.Column("actor_kind", sa.Text, nullable=False),
    sa.Column("actor_id", sa.Text),
    sa.Column("committed_at", sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(["universe_id"], ["research_universes.id"], name="fk_ru_commit_universe"),
    sa.UniqueConstraint("universe_id", "command_id", name="uq_ru_commit_universe_command"),
    sa.UniqueConstraint("position", "universe_id", name="uq_ru_commit_position_universe"),
)

ru_events = sa.Table(
    "ru_events", metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("universe_id", sa.Text, nullable=False),
    sa.Column("stream_id", sa.Text, nullable=False),
    sa.Column("commit_position", sa.BigInteger, nullable=False),
    sa.Column("commit_index", sa.Integer, nullable=False),
    sa.Column("sequence", sa.BigInteger, nullable=False),
    sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("payload", sa.JSON, nullable=False),
    sa.Column("causation_id", sa.Text),
    sa.Column("correlation_id", sa.Text),
    sa.Column("schema_version", sa.Integer, nullable=False),
    sa.ForeignKeyConstraint(["universe_id"], ["research_universes.id"], name="fk_ru_event_universe"),
    sa.ForeignKeyConstraint(["stream_id", "universe_id"], ["ru_streams.id", "ru_streams.universe_id"], name="fk_ru_event_stream_universe"),
    sa.ForeignKeyConstraint(["commit_position", "universe_id"], ["ru_commits.position", "ru_commits.universe_id"], name="fk_ru_event_commit_universe"),
    sa.UniqueConstraint("stream_id", "sequence", name="uq_ru_event_stream_sequence"),
    sa.UniqueConstraint("commit_position", "commit_index", name="uq_ru_event_commit_index"),
)


sealed_park_captures = sa.Table(
    "sealed_park_captures", metadata,
    sa.Column("id", sa.Text, primary_key=True), sa.Column("library_id", sa.Text, nullable=False),
    sa.Column("original_text", sa.Text, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
sealed_park_commands = sa.Table(
    "sealed_park_commands", metadata,
    sa.Column("library_id", sa.Text, nullable=False), sa.Column("command_id", sa.Text, nullable=False),
    sa.Column("command_fingerprint", sa.Text, nullable=False), sa.Column("capture_id", sa.Text, nullable=False),
    sa.Column("result_payload", sa.JSON, nullable=False), sa.Column("committed_at", sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint("library_id", "command_id", name="pk_sealed_park_command"),
    sa.ForeignKeyConstraint(["capture_id"], ["sealed_park_captures.id"], name="fk_sealed_park_command_capture"),
)

def bootstrap_test_schema(engine: sa.Engine) -> None:
    """Explicit test-only schema bootstrap; production uses Alembic migrations."""
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(sa.insert(ru_commit_fence).values(id=1).prefix_with("OR IGNORE") if connection.dialect.name == "sqlite" else sa.dialects.postgresql.insert(ru_commit_fence).values(id=1).on_conflict_do_nothing(index_elements=["id"]))
