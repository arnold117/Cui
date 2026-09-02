"""slice1 S1.2/S1.3 — gap candidate commands + workspace landscape readback.

Commands mirror the evidence candidate decision stream (propose → exactly one
immutable decision) but stay workspace-scoped and carry the S20 shape
(coverage statement + reproducible search record + counterexample invitation).
The landscape readback is the 现状图景 first cut (alive claims / confirmed
facts / gap candidates) and doubles as the fragment for every command reply.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from cui.research_universe.api.routes import LibraryContext, LocalPrincipal
from cui.research_universe.api.slice1 import Command, CommandResponse, _active, _universe_for_workspace
from cui.research_universe.application import (
    BoundaryViolation,
    NotFound,
    Slice1Service,
    workspace_landscape_projection,
)
from cui.research_universe.store.event_store import (
    CommandFingerprintConflict,
    ExpectedSequenceConflict,
    UniverseNotFound,
)


class ProposeGapCommand(Command):
    coverage_statement: str = Field(min_length=10)
    search_query: str = Field(min_length=1)
    search_scope: Literal["active", "legacy"] = "active"
    matched_locators: list[str] = Field(default_factory=list)
    searched_at: str | None = None
    counterexample_invitation: str = Field(min_length=1)


class GapDecisionCommand(Command):
    user_reason: str | None = None


class CorrectGapCommand(GapDecisionCommand):
    corrected_coverage_statement: str = Field(min_length=10)


def create_slice8_router(service: Slice1Service, store, context: LibraryContext, principal: LocalPrincipal) -> APIRouter:
    router = APIRouter(tags=["research-universe-slice8-gap"])

    def commit(result, workspace_id):
        return CommandResponse(
            commit_position=result.commit_position,
            event_ids=result.event_ids,
            result=result.result_payload,
            fragment=workspace_landscape_projection(store, _universe_for_workspace(store, context, workspace_id), workspace_id),
        )

    def fail(exc):
        if isinstance(exc, (ExpectedSequenceConflict, CommandFingerprintConflict, BoundaryViolation)):
            raise HTTPException(409, str(exc))
        if isinstance(exc, (NotFound, UniverseNotFound)):
            raise HTTPException(404, str(exc))
        raise exc

    @router.post("/workspaces/{workspace_id}/gap-candidates", status_code=status.HTTP_201_CREATED, response_model=CommandResponse)
    def propose(workspace_id: str, body: ProposeGapCommand):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        try:
            result = service.propose_gap_candidate(
                universe_id, workspace_id, body.coverage_statement, body.search_query,
                body.search_scope, body.matched_locators, body.counterexample_invitation,
                body.searched_at, body.command_id, body.expected_sequence,
            )
            return commit(result, workspace_id)
        except Exception as exc:
            fail(exc)

    @router.post("/gap-candidates/{candidate_id}/confirm", response_model=CommandResponse)
    def confirm(candidate_id: str, body: GapDecisionCommand):
        universe_id = _universe_for_candidate(store, context, candidate_id)
        workspace_id = _workspace_for_gap(store, context, candidate_id)
        try:
            result = service.confirm_gap_candidate(universe_id, candidate_id, body.user_reason, body.command_id, body.expected_sequence)
            return commit(result, workspace_id)
        except Exception as exc:
            fail(exc)

    @router.post("/gap-candidates/{candidate_id}/correct", response_model=CommandResponse)
    def correct(candidate_id: str, body: CorrectGapCommand):
        universe_id = _universe_for_candidate(store, context, candidate_id)
        workspace_id = _workspace_for_gap(store, context, candidate_id)
        try:
            result = service.correct_gap_candidate(universe_id, candidate_id, body.corrected_coverage_statement, body.user_reason, body.command_id, body.expected_sequence)
            return commit(result, workspace_id)
        except Exception as exc:
            fail(exc)

    @router.post("/gap-candidates/{candidate_id}/reject", response_model=CommandResponse)
    def reject(candidate_id: str, body: GapDecisionCommand):
        universe_id = _universe_for_candidate(store, context, candidate_id)
        workspace_id = _workspace_for_gap(store, context, candidate_id)
        try:
            result = service.reject_gap_candidate(universe_id, candidate_id, body.user_reason, body.command_id, body.expected_sequence)
            return commit(result, workspace_id)
        except Exception as exc:
            fail(exc)

    @router.post("/gap-candidates/{candidate_id}/withdraw", response_model=CommandResponse)
    def withdraw(candidate_id: str, body: GapDecisionCommand):
        universe_id = _universe_for_candidate(store, context, candidate_id)
        workspace_id = _workspace_for_gap(store, context, candidate_id)
        try:
            result = service.withdraw_gap_candidate(universe_id, candidate_id, body.user_reason, body.command_id, body.expected_sequence)
            return commit(result, workspace_id)
        except Exception as exc:
            fail(exc)

    @router.get("/workspaces/{workspace_id}/landscape")
    def landscape(workspace_id: str):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        return workspace_landscape_projection(store, universe_id, workspace_id)

    return router


def _universe_for_candidate(store, context: LibraryContext, ident: str):
    universe_id = _active(store, context)
    if not any(e.event_type == "gap_candidate_proposed" and e.validated_payload().gap_candidate_id == ident for e in store.read_events(universe_id)):
        raise HTTPException(404, "gap candidate not in active universe")
    return universe_id


def _workspace_for_gap(store, context: LibraryContext, ident: str) -> str:
    universe_id = _active(store, context)
    for event in store.read_events(universe_id):
        if event.event_type == "gap_candidate_proposed" and event.validated_payload().gap_candidate_id == ident:
            return event.validated_payload().workspace_id
    raise HTTPException(404, "gap candidate not in active universe")
