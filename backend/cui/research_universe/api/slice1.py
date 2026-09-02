"""Native Slice 1 HTTP contract."""
from __future__ import annotations
from uuid import uuid4
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from cui.research_universe.api.routes import LibraryContext, LocalPrincipal
from cui.research_universe.application import Slice1Service, ChallengeGenerationFailed, NotFound, BoundaryViolation, workspace_projection, review_round_projection, universe_home_projection, workspace_landscape_projection
from cui.research_universe.store.event_store import ExpectedSequenceConflict, CommandFingerprintConflict, UniverseNotFound

class Command(BaseModel): command_id: str; expected_sequence: int = Field(ge=0)
class WorkspaceCommand(Command): question: str = Field(min_length=1)
class NoteCommand(Command): text: str = Field(min_length=1)
class AnchorCommand(Command): note_id: str; note_revision_id: str; start: int = Field(ge=0); end: int = Field(gt=0); selected_text: str = Field(min_length=1)
class ClaimCommand(Command): text: str = Field(min_length=1)
class CommandResponse(BaseModel): commit_position: int; event_ids: list[str]; result: dict[str, object]; fragment: dict[str, object]

def create_slice1_router(service: Slice1Service, store, context: LibraryContext, principal: LocalPrincipal) -> APIRouter:
    router = APIRouter(tags=["research-universe-slice1"])
    def commit(result, fragment): return CommandResponse(commit_position=result.commit_position, event_ids=result.event_ids, result=result.result_payload, fragment=fragment)
    def fail(exc):
        if isinstance(exc, ExpectedSequenceConflict): raise HTTPException(409, "stale expected_sequence")
        if isinstance(exc, CommandFingerprintConflict): raise HTTPException(409, "command_id reused with different semantic command")
        if isinstance(exc, (NotFound, UniverseNotFound)): raise HTTPException(404, str(exc))
        if isinstance(exc, BoundaryViolation): raise HTTPException(422, str(exc))
        if isinstance(exc, ChallengeGenerationFailed): raise HTTPException(502, "challenge generation failed; no facts committed")
        raise exc
    @router.post("/universes/{universe_id}/workspaces", status_code=status.HTTP_201_CREATED, response_model=CommandResponse)
    def create_workspace(universe_id: str, body: WorkspaceCommand):
        if universe_id != _active(store, context): raise HTTPException(404, "universe not in active library context")
        try:
            r=service.create_workspace(universe_id, body.command_id, body.expected_sequence, body.question); return commit(r, workspace_projection(store, universe_id, r.result_payload["workspace_id"]))
        except Exception as e: fail(e)
    @router.post("/workspaces/{workspace_id}/notes", response_model=CommandResponse)
    def save_note(workspace_id: str, body: NoteCommand):
        universe_id=_universe_for_workspace(store, context, workspace_id)
        try:
            r=service.save_note(universe_id, workspace_id, body.command_id, body.expected_sequence, body.text); return commit(r, workspace_projection(store, universe_id, workspace_id))
        except Exception as e: fail(e)
    @router.post("/workspaces/{workspace_id}/anchors", response_model=CommandResponse)
    def anchor(workspace_id: str, body: AnchorCommand):
        universe_id=_universe_for_workspace(store, context, workspace_id)
        try:
            r=service.create_anchor(universe_id, workspace_id, body.command_id, body.expected_sequence, body.note_id, body.note_revision_id, body.start, body.end, body.selected_text); return commit(r, workspace_projection(store, universe_id, workspace_id))
        except Exception as e: fail(e)
    @router.post("/workspaces/{workspace_id}/claims", status_code=status.HTTP_201_CREATED, response_model=CommandResponse)
    def claim(workspace_id: str, body: ClaimCommand):
        universe_id=_universe_for_workspace(store, context, workspace_id)
        try:
            r=service.create_claim(universe_id, workspace_id, body.command_id, body.expected_sequence, body.text); return commit(r, workspace_projection(store, universe_id, workspace_id))
        except Exception as e: fail(e)
    @router.post("/claims/{claim_id}/review-rounds", status_code=status.HTTP_201_CREATED, response_model=CommandResponse)
    def round(claim_id: str, body: Command):
        universe_id=_universe_for_claim(store, context, claim_id)
        try:
            r=service.start_review_round(universe_id, claim_id, body.command_id, body.expected_sequence); return commit(r, review_round_projection(store, universe_id, r.result_payload["review_round_id"]))
        except Exception as e: fail(e)
    @router.get("/universes/{universe_id}/home")
    def home(universe_id: str):
        if universe_id != _active(store, context): raise HTTPException(404, "universe not in active library context")
        return universe_home_projection(store, universe_id)
    @router.get("/workspaces/{workspace_id}")
    def workspace(workspace_id: str):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        projection = workspace_projection(store, universe_id, workspace_id)
        projection["landscape"] = workspace_landscape_projection(store, universe_id, workspace_id)
        return projection
    @router.get("/review-rounds/{round_id}")
    def review_round(round_id: str): return review_round_projection(store, _universe_for_round(store, context, round_id), round_id)
    return router

def _active(store, context):
    uid=store.get_active_universe(context.library_id)
    if not uid: raise HTTPException(404, "no active universe")
    return uid
def _universe_for_workspace(store, context, ident):
    uid=_active(store, context)
    try: workspace_projection(store, uid, ident)
    except NotFound: raise HTTPException(404, "workspace not in active universe")
    return uid
def _universe_for_claim(store, context, ident):
    uid=_active(store, context)
    if not any(e.event_type == "claim_created" and e.validated_payload().claim_id == ident for e in store.read_events(uid)): raise HTTPException(404, "claim not in active universe")
    return uid
def _universe_for_round(store, context, ident):
    uid=_active(store, context)
    try: review_round_projection(store, uid, ident)
    except NotFound: raise HTTPException(404, "review round not in active universe")
    return uid
