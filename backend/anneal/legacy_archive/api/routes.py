"""Read-only legacy archive facade over the existing repository and event store."""
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from anneal.store.event_store import EventStore
from anneal.store.repository import Repository

class ArchiveArtifactDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact: dict[str, Any]
    claims: list[dict[str, Any]]
    materials: list[dict[str, Any]]
    projects: list[dict[str, Any]]
    conversations: list[dict[str, Any]]
    trajectory: list[dict[str, Any]]

def create_router(repository: Repository | None = None, event_store: EventStore | None = None, library_id: str | None = None) -> APIRouter:
    router = APIRouter(prefix="/legacy-archive", tags=["legacy-archive"])
    def require() -> tuple[Repository, EventStore, str]:
        if repository is None or event_store is None or library_id is None:
            raise HTTPException(503, "legacy archive unavailable")
        return repository, event_store, library_id
    def get_artifact(artifact_id: str):
        repo, events, scoped_library = require()
        artifact = repo.get_artifact(artifact_id)
        if artifact is None or artifact.library_id != scoped_library:
            raise HTTPException(404, "archive artifact not found")
        return repo, events, scoped_library, artifact
    @router.get("")
    def archive_index():
        repo, _, scoped_library = require()
        return {"artifacts": [a.model_dump(mode="json") for a in repo.list_artifacts(scoped_library)]}
    @router.get("/artifacts/{artifact_id}", response_model=ArchiveArtifactDetail)
    def detail(artifact_id: str):
        repo, events, scoped_library, artifact = get_artifact(artifact_id)
        # All linked entities are re-filtered by Library, preventing legacy join leakage.
        claims = [c for c in repo.list_claims(scoped_library) if artifact.id in c.artifact_ids]
        allowed_materials = set(artifact.material_ids)
        materials = [m for m in repo.list_materials(scoped_library) if m.id in allowed_materials]
        allowed_projects = set(artifact.project_ids)
        projects = [p for p in repo.list_projects(scoped_library) if p.id in allowed_projects]
        conversations = [c for c in repo.list_conversations(scoped_library) if allowed_projects.intersection(c.project_ids)]
        return ArchiveArtifactDetail(artifact=artifact.model_dump(mode="json"), claims=[x.model_dump(mode="json") for x in claims], materials=[x.model_dump(mode="json") for x in materials], projects=[x.model_dump(mode="json") for x in projects], conversations=[x.model_dump(mode="json") for x in conversations], trajectory=[e.model_dump(mode="json") for e in events.get_events(artifact.id)])
    @router.get("/artifacts/{artifact_id}/trajectory")
    def trajectory(artifact_id: str):
        _, events, _, artifact = get_artifact(artifact_id)
        return {"artifact_id": artifact.id, "events": [e.model_dump(mode="json") for e in events.get_events(artifact.id)]}
    return router
