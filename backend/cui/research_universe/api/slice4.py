"""Native Slice 4 manual material / evidence gate contract."""
from __future__ import annotations
from typing import Literal
from fastapi import APIRouter, HTTPException, status
from pydantic import Field
from cui.research_universe.api.routes import LibraryContext, LocalPrincipal
from cui.research_universe.api.slice1 import Command, CommandResponse, _active, _universe_for_round, _universe_for_workspace
from cui.research_universe.application import Slice1Service, NotFound, BoundaryViolation, workspace_projection, review_round_projection
from cui.research_universe.store.event_store import ExpectedSequenceConflict, CommandFingerprintConflict, UniverseNotFound


class MaterialCommand(Command):
    excerpt: str = Field(min_length=1)
    source_locator: str | None = None
    parse_status: Literal["parsed", "failed"]
    purpose: Literal["evidence", "reference"]


class ProposeCandidateCommand(Command):
    material_id: str
    relation: Literal["supports", "contradicts", "silent", "cannot_assess"]
    uncertainty: str | None = None


class ConfirmCommand(Command):
    user_reason: str | None = None


class CorrectCommand(ConfirmCommand):
    corrected_relation: Literal["supports", "contradicts", "silent", "cannot_assess"]


def create_slice4_router(service: Slice1Service, store, context: LibraryContext, principal: LocalPrincipal) -> APIRouter:
    router = APIRouter(tags=["research-universe-slice4-evidence"])
    def commit(result, fragment): return CommandResponse(commit_position=result.commit_position, event_ids=result.event_ids, result=result.result_payload, fragment=fragment)
    def fail(exc):
        if isinstance(exc, (ExpectedSequenceConflict, CommandFingerprintConflict, BoundaryViolation)): raise HTTPException(409, str(exc))
        if isinstance(exc, (NotFound, UniverseNotFound)): raise HTTPException(404, str(exc))
        raise exc
    @router.post("/workspaces/{workspace_id}/materials", status_code=status.HTTP_201_CREATED, response_model=CommandResponse)
    def add_material(workspace_id: str, body: MaterialCommand):
        universe_id = _universe_for_workspace(store, context, workspace_id)
        try:
            r = service.add_material(universe_id, workspace_id, body.excerpt, body.source_locator, body.parse_status, body.purpose, body.command_id, body.expected_sequence)
            return commit(r, workspace_projection(store, universe_id, workspace_id))
        except Exception as e: fail(e)
    @router.post("/review-rounds/{round_id}/evidence-candidates", status_code=status.HTTP_201_CREATED, response_model=CommandResponse)
    def propose(round_id: str, body: ProposeCandidateCommand):
        universe_id = _universe_for_round(store, context, round_id)
        try:
            r = service.propose_evidence_candidate(universe_id, round_id, body.material_id, body.relation, body.uncertainty, body.command_id, body.expected_sequence)
            return commit(r, review_round_projection(store, universe_id, round_id))
        except Exception as e: fail(e)
    @router.post("/evidence-candidates/{candidate_id}/confirm", response_model=CommandResponse)
    def confirm(candidate_id: str, body: ConfirmCommand):
        universe_id = _universe_for_candidate(store, context, candidate_id)
        try:
            r = service.confirm_evidence_candidate(universe_id, candidate_id, body.user_reason, body.command_id, body.expected_sequence)
            return commit(r, review_round_projection(store, universe_id, r.result_payload["round_id"]))
        except Exception as e: fail(e)
    @router.post("/evidence-candidates/{candidate_id}/correct", response_model=CommandResponse)
    def correct(candidate_id: str, body: CorrectCommand):
        universe_id = _universe_for_candidate(store, context, candidate_id)
        try:
            r = service.correct_evidence_candidate(universe_id, candidate_id, body.corrected_relation, body.user_reason, body.command_id, body.expected_sequence)
            return commit(r, review_round_projection(store, universe_id, r.result_payload["round_id"]))
        except Exception as e: fail(e)
    @router.post("/evidence-candidates/{candidate_id}/reject", response_model=CommandResponse)
    def reject(candidate_id: str, body: ConfirmCommand):
        universe_id = _universe_for_candidate(store, context, candidate_id)
        try:
            r = service.reject_evidence_candidate(universe_id, candidate_id, body.user_reason, body.command_id, body.expected_sequence)
            return commit(r, review_round_projection(store, universe_id, r.result_payload["round_id"]))
        except Exception as e: fail(e)
    @router.post("/evidence-candidates/{candidate_id}/withdraw", response_model=CommandResponse)
    def withdraw(candidate_id: str, body: ConfirmCommand):
        universe_id = _universe_for_candidate(store, context, candidate_id)
        try:
            r = service.withdraw_evidence_candidate(universe_id, candidate_id, body.user_reason, body.command_id, body.expected_sequence)
            return commit(r, review_round_projection(store, universe_id, r.result_payload["round_id"]))
        except Exception as e: fail(e)
    return router


def _universe_for_candidate(store, context, ident):
    uid = _active(store, context)
    if not any(e.event_type == "evidence_relation_proposed" and e.validated_payload().candidate_id == ident for e in store.read_events(uid)): raise HTTPException(404, "evidence candidate not in active universe")
    return uid
