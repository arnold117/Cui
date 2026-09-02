"""SQLAlchemy Core table definitions for Anneal.

Tables are defined in dependency order so ForeignKeys resolve correctly.
All PKs are Text (UUID strings).
"""

from __future__ import annotations

import sqlalchemy as sa

metadata = sa.MetaData()

# ------------------------------------------------------------------
# Root entities (no FK dependencies)
# ------------------------------------------------------------------

libraries = sa.Table(
    "libraries",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("created_at", sa.DateTime, nullable=False),
)

# ------------------------------------------------------------------
# Entities that depend on libraries
# ------------------------------------------------------------------

projects = sa.Table(
    "projects",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("library_id", sa.Text, sa.ForeignKey("libraries.id"), nullable=False),
    sa.Column("goal", sa.Text, nullable=False),
)

conversations = sa.Table(
    "conversations",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("library_id", sa.Text, sa.ForeignKey("libraries.id"), nullable=False),
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.Column("updated_at", sa.DateTime, nullable=False),
)

claims = sa.Table(
    "claims",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("library_id", sa.Text, sa.ForeignKey("libraries.id"), nullable=False),
    sa.Column("body", sa.Text, nullable=False),
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.Column("updated_at", sa.DateTime, nullable=False),
)

artifacts = sa.Table(
    "artifacts",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("library_id", sa.Text, sa.ForeignKey("libraries.id"), nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("goal", sa.Text, nullable=False),
    sa.Column("constraints", sa.JSON, nullable=False, server_default="[]"),
    sa.Column("title", sa.Text, nullable=False, server_default=""),
    sa.Column("created_at", sa.DateTime, nullable=False),
    sa.Column("updated_at", sa.DateTime, nullable=False),
)

materials = sa.Table(
    "materials",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("library_id", sa.Text, sa.ForeignKey("libraries.id"), nullable=False),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("provenance", sa.JSON, nullable=False, server_default="{}"),
    sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
)

# ------------------------------------------------------------------
# Junction tables (depend on entities above)
# ------------------------------------------------------------------

conversation_projects = sa.Table(
    "conversation_projects",
    metadata,
    sa.Column(
        "conversation_id",
        sa.Text,
        sa.ForeignKey("conversations.id"),
        primary_key=True,
    ),
    sa.Column(
        "project_id",
        sa.Text,
        sa.ForeignKey("projects.id"),
        primary_key=True,
    ),
)

claim_artifacts = sa.Table(
    "claim_artifacts",
    metadata,
    sa.Column(
        "claim_id",
        sa.Text,
        sa.ForeignKey("claims.id"),
        primary_key=True,
    ),
    sa.Column(
        "artifact_id",
        sa.Text,
        sa.ForeignKey("artifacts.id"),
        primary_key=True,
    ),
)

artifact_projects = sa.Table(
    "artifact_projects",
    metadata,
    sa.Column(
        "artifact_id",
        sa.Text,
        sa.ForeignKey("artifacts.id"),
        primary_key=True,
    ),
    sa.Column(
        "project_id",
        sa.Text,
        sa.ForeignKey("projects.id"),
        primary_key=True,
    ),
)

artifact_materials = sa.Table(
    "artifact_materials",
    metadata,
    sa.Column(
        "artifact_id",
        sa.Text,
        sa.ForeignKey("artifacts.id"),
        primary_key=True,
    ),
    sa.Column(
        "material_id",
        sa.Text,
        sa.ForeignKey("materials.id"),
        primary_key=True,
    ),
)

# ------------------------------------------------------------------
# Event sourcing table (standalone — no FK to domain entities)
# ------------------------------------------------------------------

events = sa.Table(
    "events",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("artifact_id", sa.Text, nullable=False, index=True),
    sa.Column("seq", sa.BigInteger, nullable=False),
    sa.Column("ts", sa.DateTime, nullable=False),
    sa.Column("type", sa.Text, nullable=False),
    sa.Column("data", sa.JSON, nullable=False),
)

# ------------------------------------------------------------------
# Lens feed table
# ------------------------------------------------------------------

lens_feed_entries = sa.Table(
    "lens_feed_entries",
    metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("library_id", sa.Text, sa.ForeignKey("libraries.id"), nullable=False, index=True),
    sa.Column("artifact_id", sa.Text, nullable=False),
    sa.Column("event_id", sa.Text, nullable=False),
    sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("ingested_at", sa.DateTime, nullable=False),
)
