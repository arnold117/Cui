"""Native Slice 3 review lifecycle / human verdict contract."""
from __future__ import annotations
from typing import Literal
from fastapi import APIRouter, HTTPException, status
from pydantic import Field, model_validator
from anneal.research_universe.api.routes import LibraryContext, LocalPrincipal
from anneal.research_universe.api.slice1 import Command, CommandResponse, _active
from anneal.research_universe.application import Slice1Service, NotFound, BoundaryViolation, review_round_projection
from anneal.research_universe.store.event_store import ExpectedSequenceConflict, CommandFingerprintConflict, UniverseNotFound

class AnswerCommand(Command):
    answer_text: str = Field(min_length=1)
    provisional_anchor_refs: list[str] = Field(default_factory=list)

class DeferCommand(Command):
    reason: str = Field(min_length=1)
    condition: str = Field(min_length=1)

class WithdrawCommand(Command):
    reason: str = Field(min_length=1)

class VerdictCommand(Command):
    verdict_type: Literal["survived", "refuted", "not_worth", "boundary", "circumstantial"]
    user_reason: str = Field(min_length=1)
    revival_condition: str | None = None

    @model_validator(mode="after")
    def _revival_condition_rule(self) -> "VerdictCommand":
        if self.verdict_type == "circumstantial":
            if not self.revival_condition or not self.revival_condition.strip():
                raise ValueError("circumstantial verdict requires a non-empty revival_condition")
        elif self.revival_condition is not None:
            raise ValueError("revival_condition is only valid for circumstantial verdicts")
        return self


def create_slice3_router(service: Slice1Service, store, context: LibraryContext, principal: LocalPrincipal) -> APIRouter:
    router = APIRouter(tags=["research-universe-slice3-review"])
    def commit(result, fragment): return CommandResponse(commit_position=result.commit_position, event_ids=result.event_ids, result=result.result_payload, fragment=fragment)
    def fail(exc):
        if isinstance(exc, (ExpectedSequenceConflict, CommandFingerprintConflict, BoundaryViolation)): raise HTTPException(409, str(exc))
        if isinstance(exc, (NotFound, UniverseNotFound)): raise HTTPException(404, str(exc))
        raise exc
    @router.post("/challenges/{challenge_id}/answers", response_model=CommandResponse)
    def answer(challenge_id: str, body: AnswerCommand):
        universe_id = _universe_for_challenge(store, context, challenge_id)
        try:
            r = service.answer_challenge(universe_id, challenge_id, body.answer_text, body.provisional_anchor_refs, body.command_id, body.expected_sequence); return commit(r, review_round_projection(store, universe_id, r.result_payload["review_round_id"]))
        except Exception as e: fail(e)
    @router.post("/challenges/{challenge_id}/defer", response_model=CommandResponse)
    def defer(challenge_id: str, body: DeferCommand):
        universe_id = _universe_for_challenge(store, context, challenge_id)
        try:
            r = service.defer_challenge(universe_id, challenge_id, body.reason, body.condition, body.command_id, body.expected_sequence); return commit(r, review_round_projection(store, universe_id, r.result_payload["review_round_id"]))
        except Exception as e: fail(e)
    @router.post("/challenges/{challenge_id}/withdraw", response_model=CommandResponse)
    def withdraw(challenge_id: str, body: WithdrawCommand):
        universe_id = _universe_for_challenge(store, context, challenge_id)
        try:
            r = service.withdraw_challenge(universe_id, challenge_id, body.reason, body.command_id, body.expected_sequence); return commit(r, review_round_projection(store, universe_id, r.result_payload["review_round_id"]))
        except Exception as e: fail(e)
    @router.post("/review-rounds/{round_id}/verdicts", response_model=CommandResponse)
    def verdict(round_id: str, body: VerdictCommand):
        universe_id = _universe_for_round(store, context, round_id)
        try:
            r = service.confirm_verdict(universe_id, round_id, body.verdict_type, body.user_reason, body.revival_condition, body.command_id, body.expected_sequence); return commit(r, review_round_projection(store, universe_id, round_id))
        except Exception as e: fail(e)
    return router


def _universe_for_challenge(store, context, ident):
    uid = _active(store, context)
    if not any(e.event_type == "challenge_created" and e.validated_payload().challenge_id == ident for e in store.read_events(uid)): raise HTTPException(404, "challenge not in active universe")
    return uid

def _universe_for_round(store, context, ident):
    uid = _active(store, context)
    try: review_round_projection(store, uid, ident)
    except NotFound: raise HTTPException(404, "review round not in active universe")
    return uid
