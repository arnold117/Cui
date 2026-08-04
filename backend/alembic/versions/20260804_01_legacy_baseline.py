"""Frozen legacy schema baseline.

This revision intentionally uses explicit Alembic operations only.  It is a
snapshot of the pre-native schema, not an import of runtime metadata.
"""
from alembic import op
import sqlalchemy as sa

revision = "legacy_baseline"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("libraries", sa.Column("id", sa.Text(), primary_key=True), sa.Column("name", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_table("projects", sa.Column("id", sa.Text(), primary_key=True), sa.Column("library_id", sa.Text(), nullable=False), sa.Column("goal", sa.Text(), nullable=False), sa.ForeignKeyConstraint(["library_id"], ["libraries.id"]))
    op.create_table("conversations", sa.Column("id", sa.Text(), primary_key=True), sa.Column("library_id", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False), sa.ForeignKeyConstraint(["library_id"], ["libraries.id"]))
    op.create_table("claims", sa.Column("id", sa.Text(), primary_key=True), sa.Column("library_id", sa.Text(), nullable=False), sa.Column("body", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False), sa.ForeignKeyConstraint(["library_id"], ["libraries.id"]))
    op.create_table("artifacts", sa.Column("id", sa.Text(), primary_key=True), sa.Column("library_id", sa.Text(), nullable=False), sa.Column("kind", sa.Text(), nullable=False), sa.Column("goal", sa.Text(), nullable=False), sa.Column("constraints", sa.JSON(), nullable=False, server_default="[]"), sa.Column("title", sa.Text(), nullable=False, server_default=""), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False), sa.ForeignKeyConstraint(["library_id"], ["libraries.id"]))
    op.create_table("materials", sa.Column("id", sa.Text(), primary_key=True), sa.Column("library_id", sa.Text(), nullable=False), sa.Column("kind", sa.Text(), nullable=False), sa.Column("provenance", sa.JSON(), nullable=False, server_default="{}"), sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"), sa.ForeignKeyConstraint(["library_id"], ["libraries.id"]))
    op.create_table("conversation_projects", sa.Column("conversation_id", sa.Text(), primary_key=True), sa.Column("project_id", sa.Text(), primary_key=True), sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"]), sa.ForeignKeyConstraint(["project_id"], ["projects.id"]))
    op.create_table("claim_artifacts", sa.Column("claim_id", sa.Text(), primary_key=True), sa.Column("artifact_id", sa.Text(), primary_key=True), sa.ForeignKeyConstraint(["claim_id"], ["claims.id"]), sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"]))
    op.create_table("artifact_projects", sa.Column("artifact_id", sa.Text(), primary_key=True), sa.Column("project_id", sa.Text(), primary_key=True), sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"]), sa.ForeignKeyConstraint(["project_id"], ["projects.id"]))
    op.create_table("artifact_materials", sa.Column("artifact_id", sa.Text(), primary_key=True), sa.Column("material_id", sa.Text(), primary_key=True), sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"]), sa.ForeignKeyConstraint(["material_id"], ["materials.id"]))
    op.create_table("events", sa.Column("id", sa.Text(), primary_key=True), sa.Column("artifact_id", sa.Text(), nullable=False), sa.Column("seq", sa.BigInteger(), nullable=False), sa.Column("ts", sa.DateTime(), nullable=False), sa.Column("type", sa.Text(), nullable=False), sa.Column("data", sa.JSON(), nullable=False))
    op.create_index("ix_events_artifact_id", "events", ["artifact_id"])
    op.create_table("lens_feed_entries", sa.Column("id", sa.Text(), primary_key=True), sa.Column("library_id", sa.Text(), nullable=False), sa.Column("artifact_id", sa.Text(), nullable=False), sa.Column("event_id", sa.Text(), nullable=False), sa.Column("event_type", sa.Text(), nullable=False), sa.Column("ingested_at", sa.DateTime(), nullable=False), sa.ForeignKeyConstraint(["library_id"], ["libraries.id"]))
    op.create_index("ix_lens_feed_entries_library_id", "lens_feed_entries", ["library_id"])

def downgrade() -> None:
    raise RuntimeError("legacy_baseline cannot be downgraded")
