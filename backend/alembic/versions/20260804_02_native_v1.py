"""native research universe v1

Revision ID: native_v1
Revises: legacy_baseline
"""
from alembic import op
import sqlalchemy as sa

revision = "native_v1"
down_revision = "legacy_baseline"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("research_universes",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("library_id", sa.Text(), nullable=False),
        sa.Column("model_generation", sa.Text(), nullable=False, server_default="research_universe_v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.create_index("uq_active_research_universe_per_library", "research_universes", ["library_id"], unique=True, postgresql_where=sa.text("archived_at IS NULL"))
    op.create_table("ru_streams", sa.Column("id", sa.Text(), primary_key=True), sa.Column("universe_id", sa.Text(), nullable=False), sa.Column("aggregate_type", sa.Text(), nullable=False), sa.Column("aggregate_id", sa.Text(), nullable=False), sa.Column("next_sequence", sa.BigInteger(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.ForeignKeyConstraint(["universe_id"], ["research_universes.id"], name="fk_ru_stream_universe"), sa.UniqueConstraint("id", "universe_id", name="uq_ru_stream_id_universe"), sa.UniqueConstraint("universe_id", "aggregate_type", "aggregate_id", name="uq_ru_stream_address"))
    op.create_table("ru_commit_fence", sa.Column("id", sa.SmallInteger(), primary_key=True), sa.CheckConstraint("id = 1", name="ck_ru_commit_fence_singleton"))
    op.execute("INSERT INTO ru_commit_fence (id) VALUES (1)")
    op.create_table("ru_commits", sa.Column("position", sa.BigInteger(), primary_key=True, autoincrement=True), sa.Column("id", sa.Text(), nullable=False, unique=True), sa.Column("universe_id", sa.Text(), nullable=False), sa.Column("command_id", sa.Text(), nullable=False), sa.Column("command_fingerprint", sa.Text(), nullable=False), sa.Column("result_payload", sa.JSON(), nullable=False), sa.Column("actor_kind", sa.Text(), nullable=False), sa.Column("actor_id", sa.Text()), sa.Column("committed_at", sa.DateTime(timezone=True), nullable=False), sa.ForeignKeyConstraint(["universe_id"], ["research_universes.id"], name="fk_ru_commit_universe"), sa.UniqueConstraint("universe_id", "command_id", name="uq_ru_commit_universe_command"), sa.UniqueConstraint("position", "universe_id", name="uq_ru_commit_position_universe"))
    op.create_table("ru_events", sa.Column("id", sa.Text(), primary_key=True), sa.Column("universe_id", sa.Text(), nullable=False), sa.Column("stream_id", sa.Text(), nullable=False), sa.Column("commit_position", sa.BigInteger(), nullable=False), sa.Column("commit_index", sa.Integer(), nullable=False), sa.Column("sequence", sa.BigInteger(), nullable=False), sa.Column("event_type", sa.Text(), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.Column("causation_id", sa.Text()), sa.Column("correlation_id", sa.Text()), sa.Column("schema_version", sa.Integer(), nullable=False), sa.ForeignKeyConstraint(["universe_id"], ["research_universes.id"], name="fk_ru_event_universe"), sa.ForeignKeyConstraint(["stream_id", "universe_id"], ["ru_streams.id", "ru_streams.universe_id"], name="fk_ru_event_stream_universe"), sa.ForeignKeyConstraint(["commit_position", "universe_id"], ["ru_commits.position", "ru_commits.universe_id"], name="fk_ru_event_commit_universe"), sa.UniqueConstraint("stream_id", "sequence", name="uq_ru_event_stream_sequence"), sa.UniqueConstraint("commit_position", "commit_index", name="uq_ru_event_commit_index"))

def downgrade() -> None:
    op.drop_table("ru_events")
    op.drop_table("ru_commits")
    op.drop_table("ru_commit_fence")
    op.drop_table("ru_streams")
    op.drop_index("uq_active_research_universe_per_library", table_name="research_universes")
    op.drop_table("research_universes")
