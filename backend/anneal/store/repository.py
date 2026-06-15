"""Repository Protocol + implementations for Anneal domain entities."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import Engine, select, insert

from anneal.domain.models import (
    Artifact,
    Claim,
    Conversation,
    Library,
    Material,
    Project,
)
from anneal.store import schema


class Repository(Protocol):
    def create_library(self, library: Library) -> None: ...
    def get_library(self, library_id: str) -> Library | None: ...
    def create_artifact(self, artifact: Artifact) -> None: ...
    def get_artifact(self, artifact_id: str) -> Artifact | None: ...
    def list_artifacts(self, library_id: str) -> list[Artifact]: ...
    def create_claim(self, claim: Claim) -> None: ...
    def get_claim(self, claim_id: str) -> Claim | None: ...
    def create_material(self, material: Material) -> None: ...
    def get_material(self, material_id: str) -> Material | None: ...
    def create_conversation(self, conv: Conversation) -> None: ...
    def get_conversation(self, conv_id: str) -> Conversation | None: ...
    def create_project(self, project: Project) -> None: ...
    def get_project(self, project_id: str) -> Project | None: ...


# ------------------------------------------------------------------
# In-memory implementation (tests)
# ------------------------------------------------------------------


class InMemoryRepository:
    """Dict-backed repository for tests."""

    def __init__(self) -> None:
        self._libraries: dict[str, Library] = {}
        self._artifacts: dict[str, Artifact] = {}
        self._claims: dict[str, Claim] = {}
        self._materials: dict[str, Material] = {}
        self._conversations: dict[str, Conversation] = {}
        self._projects: dict[str, Project] = {}

    # --- Library ---

    def create_library(self, library: Library) -> None:
        self._libraries[library.id] = library

    def get_library(self, library_id: str) -> Library | None:
        return self._libraries.get(library_id)

    # --- Artifact ---

    def create_artifact(self, artifact: Artifact) -> None:
        self._artifacts[artifact.id] = artifact

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        return self._artifacts.get(artifact_id)

    def list_artifacts(self, library_id: str) -> list[Artifact]:
        return [a for a in self._artifacts.values() if a.library_id == library_id]

    # --- Claim ---

    def create_claim(self, claim: Claim) -> None:
        self._claims[claim.id] = claim

    def get_claim(self, claim_id: str) -> Claim | None:
        return self._claims.get(claim_id)

    # --- Material ---

    def create_material(self, material: Material) -> None:
        self._materials[material.id] = material

    def get_material(self, material_id: str) -> Material | None:
        return self._materials.get(material_id)

    # --- Conversation ---

    def create_conversation(self, conv: Conversation) -> None:
        self._conversations[conv.id] = conv

    def get_conversation(self, conv_id: str) -> Conversation | None:
        return self._conversations.get(conv_id)

    # --- Project ---

    def create_project(self, project: Project) -> None:
        self._projects[project.id] = project

    def get_project(self, project_id: str) -> Project | None:
        return self._projects.get(project_id)


# ------------------------------------------------------------------
# PostgreSQL implementation (SQLAlchemy Core)
# ------------------------------------------------------------------


class PostgresRepository:
    """PostgreSQL-backed repository using SQLAlchemy Core."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # --- Library ---

    def create_library(self, library: Library) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                insert(schema.libraries).values(
                    id=library.id,
                    name=library.name,
                    created_at=library.created_at,
                )
            )

    def get_library(self, library_id: str) -> Library | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(schema.libraries).where(schema.libraries.c.id == library_id)
            ).first()
            if row is None:
                return None
            return Library(id=row.id, name=row.name, created_at=row.created_at)

    # --- Artifact ---

    def create_artifact(self, artifact: Artifact) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                insert(schema.artifacts).values(
                    id=artifact.id,
                    library_id=artifact.library_id,
                    kind=artifact.kind,
                    goal=artifact.goal,
                    constraints=artifact.constraints,
                    title=artifact.title,
                    created_at=artifact.created_at,
                    updated_at=artifact.updated_at,
                )
            )
            for pid in artifact.project_ids:
                conn.execute(
                    insert(schema.artifact_projects).values(
                        artifact_id=artifact.id,
                        project_id=pid,
                    )
                )
            for mid in artifact.material_ids:
                conn.execute(
                    insert(schema.artifact_materials).values(
                        artifact_id=artifact.id,
                        material_id=mid,
                    )
                )

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(schema.artifacts).where(schema.artifacts.c.id == artifact_id)
            ).first()
            if row is None:
                return None

            project_rows = conn.execute(
                select(schema.artifact_projects.c.project_id).where(
                    schema.artifact_projects.c.artifact_id == artifact_id
                )
            ).fetchall()

            material_rows = conn.execute(
                select(schema.artifact_materials.c.material_id).where(
                    schema.artifact_materials.c.artifact_id == artifact_id
                )
            ).fetchall()

            return Artifact(
                id=row.id,
                library_id=row.library_id,
                kind=row.kind,
                goal=row.goal,
                constraints=row.constraints,
                title=row.title,
                project_ids=[r.project_id for r in project_rows],
                material_ids=[r.material_id for r in material_rows],
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def list_artifacts(self, library_id: str) -> list[Artifact]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(schema.artifacts).where(
                    schema.artifacts.c.library_id == library_id
                )
            ).fetchall()

            artifacts: list[Artifact] = []
            for row in rows:
                project_rows = conn.execute(
                    select(schema.artifact_projects.c.project_id).where(
                        schema.artifact_projects.c.artifact_id == row.id
                    )
                ).fetchall()

                material_rows = conn.execute(
                    select(schema.artifact_materials.c.material_id).where(
                        schema.artifact_materials.c.artifact_id == row.id
                    )
                ).fetchall()

                artifacts.append(
                    Artifact(
                        id=row.id,
                        library_id=row.library_id,
                        kind=row.kind,
                        goal=row.goal,
                        constraints=row.constraints,
                        title=row.title,
                        project_ids=[r.project_id for r in project_rows],
                        material_ids=[r.material_id for r in material_rows],
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                    )
                )
            return artifacts

    # --- Claim ---

    def create_claim(self, claim: Claim) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                insert(schema.claims).values(
                    id=claim.id,
                    library_id=claim.library_id,
                    body=claim.body,
                    created_at=claim.created_at,
                    updated_at=claim.updated_at,
                )
            )
            for aid in claim.artifact_ids:
                conn.execute(
                    insert(schema.claim_artifacts).values(
                        claim_id=claim.id,
                        artifact_id=aid,
                    )
                )

    def get_claim(self, claim_id: str) -> Claim | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(schema.claims).where(schema.claims.c.id == claim_id)
            ).first()
            if row is None:
                return None

            artifact_rows = conn.execute(
                select(schema.claim_artifacts.c.artifact_id).where(
                    schema.claim_artifacts.c.claim_id == claim_id
                )
            ).fetchall()

            return Claim(
                id=row.id,
                library_id=row.library_id,
                body=row.body,
                artifact_ids=[r.artifact_id for r in artifact_rows],
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    # --- Material ---

    def create_material(self, material: Material) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                insert(schema.materials).values(
                    id=material.id,
                    library_id=material.library_id,
                    kind=material.kind,
                    provenance=material.provenance,
                    payload=material.payload,
                )
            )

    def get_material(self, material_id: str) -> Material | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(schema.materials).where(schema.materials.c.id == material_id)
            ).first()
            if row is None:
                return None
            return Material(
                id=row.id,
                library_id=row.library_id,
                kind=row.kind,
                provenance=row.provenance,
                payload=row.payload,
            )

    # --- Conversation ---

    def create_conversation(self, conv: Conversation) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                insert(schema.conversations).values(
                    id=conv.id,
                    library_id=conv.library_id,
                    created_at=conv.created_at,
                    updated_at=conv.updated_at,
                )
            )
            for pid in conv.project_ids:
                conn.execute(
                    insert(schema.conversation_projects).values(
                        conversation_id=conv.id,
                        project_id=pid,
                    )
                )

    def get_conversation(self, conv_id: str) -> Conversation | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(schema.conversations).where(
                    schema.conversations.c.id == conv_id
                )
            ).first()
            if row is None:
                return None

            project_rows = conn.execute(
                select(schema.conversation_projects.c.project_id).where(
                    schema.conversation_projects.c.conversation_id == conv_id
                )
            ).fetchall()

            return Conversation(
                id=row.id,
                library_id=row.library_id,
                project_ids=[r.project_id for r in project_rows],
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    # --- Project ---

    def create_project(self, project: Project) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                insert(schema.projects).values(
                    id=project.id,
                    library_id=project.library_id,
                    goal=project.goal,
                )
            )

    def get_project(self, project_id: str) -> Project | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(schema.projects).where(schema.projects.c.id == project_id)
            ).first()
            if row is None:
                return None
            return Project(
                id=row.id,
                library_id=row.library_id,
                goal=row.goal,
            )
