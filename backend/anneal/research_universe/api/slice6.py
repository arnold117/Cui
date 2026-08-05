"""Native Slice 6 expanded LLM evidence candidates / additional challenges contract.

Both commands are EXPLICIT user commands: nothing is auto-created beyond the
single challenge_created / evidence_relation_proposed event the user asked for.
Generated candidates flow through the SAME Slice 4 evidence decision lifecycle.
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException, status
from anneal.research_universe.api.routes import LibraryContext, LocalPrincipal
from anneal.research_universe.api.slice1 import Command, CommandResponse, _universe_for_round
from anneal.research_universe.application import Slice1Service, NotFound, BoundaryViolation, ChallengeGenerationFailed, EvidenceGenerationFailed, review_round_projection
from anneal.research_universe.store.event_store import ExpectedSequenceConflict, CommandFingerprintConflict, UniverseNotFound


class GenerateEvidenceCandidateCommand(Command):
    material_id: str


def create_slice6_router(service: Slice1Service, store, context: LibraryContext, principal: LocalPrincipal) -> APIRouter:
    router = APIRouter(tags=["research-universe-slice6-llm-generation"])
    def commit(result, fragment): return CommandResponse(commit_position=result.commit_position, event_ids=result.event_ids, result=result.result_payload, fragment=fragment)
    def fail(exc):
        if isinstance(exc, (ExpectedSequenceConflict, CommandFingerprintConflict, BoundaryViolation)): raise HTTPException(409, str(exc))
        if isinstance(exc, (NotFound, UniverseNotFound)): raise HTTPException(404, str(exc))
        if isinstance(exc, (ChallengeGenerationFailed, EvidenceGenerationFailed)): raise HTTPException(502, str(exc))
        raise exc
    @router.post("/review-rounds/{round_id}/challenges", status_code=status.HTTP_201_CREATED, response_model=CommandResponse)
    def generate_additional_challenge(round_id: str, body: Command):
        universe_id = _universe_for_round(store, context, round_id)
        try:
            r = service.generate_additional_challenge(universe_id, round_id, body.command_id, body.expected_sequence)
            return commit(r, review_round_projection(store, universe_id, round_id))
        except Exception as e: fail(e)
    @router.post("/review-rounds/{round_id}/evidence-candidate-generation", status_code=status.HTTP_201_CREATED, response_model=CommandResponse)
    def generate_evidence_candidate(round_id: str, body: GenerateEvidenceCandidateCommand):
        universe_id = _universe_for_round(store, context, round_id)
        try:
            r = service.generate_evidence_candidate(universe_id, round_id, body.material_id, body.command_id, body.expected_sequence)
            return commit(r, review_round_projection(store, universe_id, round_id))
        except Exception as e: fail(e)
    return router
