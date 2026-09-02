"""Native Slice 5 workspace crystallization / direction impact contract."""
from __future__ import annotations
from typing import Literal
from fastapi import APIRouter, HTTPException, status
from pydantic import Field, model_validator
from cui.research_universe.api.routes import LibraryContext, LocalPrincipal
from cui.research_universe.api.slice1 import Command, CommandResponse, _active, _universe_for_workspace
from cui.research_universe.application import Slice1Service, NotFound, BoundaryViolation, direction_projection, workspace_projection
from cui.research_universe.store.event_store import ExpectedSequenceConflict, CommandFingerprintConflict, UniverseNotFound


class PauseCommand(Command):
    user_reason: str | None = None


class ReopenCommand(Command):
    user_reason: str | None = None


class BranchCommand(Command):
    new_question: str = Field(min_length=1)
    user_reason: str = Field(min_length=1)


class AbsorbCommand(Command):
    target_workspace_id: str
    user_reason: str = Field(min_length=1)


class ConcludeCommand(Command):
    conclusion_type: Literal["tentative_answer", "negated_path", "boundary", "key_unknown", "deferred", "split_or_turn"]
    conclusion_text: str = Field(min_length=1)
    user_reason: str | None = None
    basis_refs: list[str] = Field(default_factory=list)
    revival_condition: str | None = None

    @model_validator(mode="after")
    def _revival_condition_rule(self) -> "ConcludeCommand":
        if self.conclusion_type == "deferred":
            if not self.revival_condition or not self.revival_condition.strip():
                raise ValueError("deferred conclusion requires a non-empty revival_condition")
        elif self.revival_condition is not None:
            raise ValueError("revival_condition is only valid for deferred conclusions")
        return self


class AttachDirectionCommand(Command):
    direction_id: str
    user_reason: str | None = None


class DetachDirectionLinkCommand(Command):
    user_reason: str | None = None


class CreateDirectionCommand(Command):
    proposition: str = Field(min_length=1)


class DeclareStatusCommand(Command):
    status: Literal["active", "on_hold", "retired"]
    user_reason: str = Field(min_length=1)


class RephraseDirectionCommand(Command):
    new_proposition: str | None = None
    change_type: Literal["clarify", "narrow_or_widen", "turning", "unnamed"]
    user_reason: str = Field(min_length=1)
    source_conclusion_ref: str | None = None

    @model_validator(mode="after")
    def _unnamed_rule(self) -> "RephraseDirectionCommand":
        if self.change_type == "unnamed":
            if self.new_proposition is not None:
                raise ValueError("unnamed rephrase must carry a null proposition")
        elif not self.new_proposition or not self.new_proposition.strip():
            raise ValueError("non-unnamed rephrase requires a non-empty proposition")
        return self


class AttachCrystallizationCommand(Command):
    workspace_id: str
    conclusion_id: str
    user_reason: str | None = None


def create_slice5_router(service: Slice1Service, store, context: LibraryContext, principal: LocalPrincipal) -> APIRouter:
    router = APIRouter(tags=["research-universe-slice5-crystallization"])
    def commit(result, fragment): return CommandResponse(commit_position=result.commit_position, event_ids=result.event_ids, result=result.result_payload, fragment=fragment)
    def fail(exc):
        if isinstance(exc, (ExpectedSequenceConflict, CommandFingerprintConflict, BoundaryViolation)): raise HTTPException(409, str(exc))
        if isinstance(exc, (NotFound, UniverseNotFound)): raise HTTPException(404, str(exc))
        raise exc
    @router.post("/workspaces/{workspace_id}/pause", response_model=CommandResponse)
    def pause(workspace_id: str, body: PauseCommand):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        try:
            r = service.pause_workspace(universe_id, workspace_id, body.user_reason, body.command_id, body.expected_sequence)
            return commit(r, workspace_projection(store, universe_id, workspace_id))
        except Exception as e: fail(e)
    @router.post("/workspaces/{workspace_id}/reopen", response_model=CommandResponse)
    def reopen(workspace_id: str, body: ReopenCommand):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        try:
            r = service.reopen_workspace(universe_id, workspace_id, body.user_reason, body.command_id, body.expected_sequence)
            return commit(r, workspace_projection(store, universe_id, workspace_id))
        except Exception as e: fail(e)
    @router.post("/workspaces/{workspace_id}/branch", response_model=CommandResponse)
    def branch(workspace_id: str, body: BranchCommand):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        try:
            r = service.branch_workspace(universe_id, workspace_id, body.new_question, body.user_reason, body.command_id, body.expected_sequence)
            return commit(r, workspace_projection(store, universe_id, workspace_id))
        except Exception as e: fail(e)
    @router.post("/workspaces/{workspace_id}/absorb", response_model=CommandResponse)
    def absorb(workspace_id: str, body: AbsorbCommand):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        try:
            r = service.absorb_workspace(universe_id, workspace_id, body.target_workspace_id, body.user_reason, body.command_id, body.expected_sequence)
            return commit(r, workspace_projection(store, universe_id, workspace_id))
        except Exception as e: fail(e)
    @router.post("/workspaces/{workspace_id}/conclusions", response_model=CommandResponse)
    def conclude(workspace_id: str, body: ConcludeCommand):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        try:
            r = service.conclude_workspace(universe_id, workspace_id, body.conclusion_type, body.conclusion_text, body.user_reason, body.basis_refs, body.revival_condition, body.command_id, body.expected_sequence)
            return commit(r, workspace_projection(store, universe_id, workspace_id))
        except Exception as e: fail(e)
    @router.post("/workspaces/{workspace_id}/direction-links", status_code=status.HTTP_201_CREATED, response_model=CommandResponse)
    def attach_direction(workspace_id: str, body: AttachDirectionCommand):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        try:
            r = service.attach_direction(universe_id, workspace_id, body.direction_id, body.user_reason, body.command_id, body.expected_sequence)
            return commit(r, workspace_projection(store, universe_id, workspace_id))
        except Exception as e: fail(e)
    @router.post("/workspace-direction-links/{link_id}/detach", response_model=CommandResponse)
    def detach_direction_link(link_id: str, body: DetachDirectionLinkCommand):
        universe_id = _universe_for_direction_link(store, context, link_id)
        try:
            r = service.detach_direction_link(universe_id, link_id, body.user_reason, body.command_id, body.expected_sequence)
            return commit(r, direction_projection(store, universe_id, r.result_payload["direction_id"]))
        except Exception as e: fail(e)
    @router.post("/universes/{universe_id}/directions", status_code=status.HTTP_201_CREATED, response_model=CommandResponse)
    def create_direction(universe_id: str, body: CreateDirectionCommand):
        if universe_id != _active(store, context): raise HTTPException(404, "universe not in active library context")
        try:
            r = service.create_direction(universe_id, body.proposition, body.command_id, body.expected_sequence)
            return commit(r, direction_projection(store, universe_id, r.result_payload["direction_id"]))
        except Exception as e: fail(e)
    @router.post("/directions/{direction_id}/status-declarations", response_model=CommandResponse)
    def declare_status(direction_id: str, body: DeclareStatusCommand):
        universe_id = _universe_for_direction(store, context, direction_id)
        try:
            r = service.declare_direction_status(universe_id, direction_id, body.status, body.user_reason, body.command_id, body.expected_sequence)
            return commit(r, direction_projection(store, universe_id, direction_id))
        except Exception as e: fail(e)
    @router.post("/directions/{direction_id}/rephrasings", response_model=CommandResponse)
    def rephrase(direction_id: str, body: RephraseDirectionCommand):
        universe_id = _universe_for_direction(store, context, direction_id)
        try:
            r = service.rephrase_direction(universe_id, direction_id, body.new_proposition, body.change_type, body.user_reason, body.source_conclusion_ref, body.command_id, body.expected_sequence)
            return commit(r, direction_projection(store, universe_id, direction_id))
        except Exception as e: fail(e)
    @router.post("/directions/{direction_id}/crystallizations", status_code=status.HTTP_201_CREATED, response_model=CommandResponse)
    def attach_crystallization(direction_id: str, body: AttachCrystallizationCommand):
        universe_id = _universe_for_direction(store, context, direction_id)
        try:
            r = service.attach_crystallization(universe_id, direction_id, body.workspace_id, body.conclusion_id, body.user_reason, body.command_id, body.expected_sequence)
            return commit(r, direction_projection(store, universe_id, direction_id))
        except Exception as e: fail(e)
    @router.get("/directions/{direction_id}")
    def direction(direction_id: str):
        universe_id = _universe_for_direction(store, context, direction_id)
        return direction_projection(store, universe_id, direction_id)
    return router


def _universe_for_direction(store, context, ident):
    uid = _active(store, context)
    try: direction_projection(store, uid, ident)
    except NotFound: raise HTTPException(404, "direction not in active universe")
    return uid


def _universe_for_direction_link(store, context, ident):
    uid = _active(store, context)
    if not any(e.event_type == "workspace_direction_attached" and e.validated_payload().direction_link_id == ident for e in store.read_events(uid)): raise HTTPException(404, "direction link not in active universe")
    return uid
