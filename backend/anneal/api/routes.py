"""FastAPI route definitions — thin HTTP layer delegating to services.

No business logic lives here.  Domain exceptions are mapped to HTTP
status codes; everything else is pass-through.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from anneal.api.deps import (
    get_event_service,
    get_event_store,
    get_grill_service,
    get_lens_feed_service,
    get_park_service,
    get_promote_service,
    get_repository,
)
from anneal.domain.invariants import (
    DebtBlockError,
    KilledClaimError,
    ParkIsolationViolation,
    UngrilledError,
)
from anneal.llm.errors import LLMNotConfiguredError, LLMResponseError
from anneal.services.event_service import EventService
from anneal.services.grill_service import GrillService
from anneal.services.lens_feed_service import LensFeedService
from anneal.services.park_service import ParkService
from anneal.services.promote_service import PromoteService
from anneal.store.event_store import EventStore
from anneal.store.repository import Repository

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class ParkRequest(BaseModel):
    library_id: str
    body: str
    kind: str = "idea"


class GrillStartRequest(BaseModel):
    kind: str


class ChallengeRequest(BaseModel):
    claim_id: str
    question: str


class AnswerRequest(BaseModel):
    claim_id: str
    response: str


class VerdictRequest(BaseModel):
    claim_id: str
    outcome: str
    rationale: str = ""


class BypassRequest(BaseModel):
    claim_id: str


class ConfirmRequest(BaseModel):
    event_id: str


class BatchConfirmRequest(BaseModel):
    event_ids: list[str]


class RetractRequest(BaseModel):
    event_id: str


class AutoChallengeRequest(BaseModel):
    claim_id: str
    claim_body: str
    context: str = ""


class AutoVerdictRequest(BaseModel):
    claim_id: str
    claim_body: str
    question: str
    answer: str


class LensFeedIngestRequest(BaseModel):
    library_id: str


# ---------------------------------------------------------------------------
# Exception → HTTP mapping helper
# ---------------------------------------------------------------------------


def _handle_domain_error(exc: Exception) -> HTTPException:
    """Convert domain exceptions to HTTPException."""
    if isinstance(exc, (DebtBlockError, UngrilledError, KilledClaimError, ParkIsolationViolation)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


# ---------------------------------------------------------------------------
# Park endpoints
# ---------------------------------------------------------------------------


@router.post("/park")
def park(
    req: ParkRequest,
    park_svc: ParkService = Depends(get_park_service),
):
    try:
        artifact, claim = park_svc.park(req.library_id, req.body, req.kind)
    except (ValueError,) as exc:
        raise _handle_domain_error(exc)

    return {
        "artifact": artifact.model_dump(mode="json"),
        "claim": claim.model_dump(mode="json"),
    }


@router.get("/park")
def list_parked(
    library_id: str,
    park_svc: ParkService = Depends(get_park_service),
):
    """List parked artifact IDs for a library."""
    parked_ids = park_svc.list_parked(library_id)
    return {"artifact_ids": parked_ids}


# ---------------------------------------------------------------------------
# Read-only entity endpoints
# ---------------------------------------------------------------------------


@router.get("/artifact/{artifact_id}")
def get_artifact(
    artifact_id: str,
    repo: Repository = Depends(get_repository),
):
    artifact = repo.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"Artifact {artifact_id} not found")
    return {"artifact": artifact.model_dump(mode="json")}


@router.get("/claim/{claim_id}")
def get_claim(
    claim_id: str,
    repo: Repository = Depends(get_repository),
):
    claim = repo.get_claim(claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")
    return {"claim": claim.model_dump(mode="json")}


@router.get("/artifacts")
def list_artifacts(
    library_id: str,
    repo: Repository = Depends(get_repository),
):
    artifacts = repo.list_artifacts(library_id)
    return {"artifacts": [a.model_dump(mode="json") for a in artifacts]}


# ---------------------------------------------------------------------------
# Grill endpoints
# ---------------------------------------------------------------------------


@router.post("/grill/{artifact_id}/start")
def grill_start(
    artifact_id: str,
    req: GrillStartRequest,
    grill_svc: GrillService = Depends(get_grill_service),
):
    try:
        grill_svc.start_grill(artifact_id, req.kind)
    except (ValueError, DebtBlockError, UngrilledError, KilledClaimError, ParkIsolationViolation) as exc:
        raise _handle_domain_error(exc)
    return {"status": "grill_started", "artifact_id": artifact_id}


@router.post("/grill/{artifact_id}/challenge")
def grill_challenge(
    artifact_id: str,
    req: ChallengeRequest,
    grill_svc: GrillService = Depends(get_grill_service),
):
    try:
        event = grill_svc.challenge(artifact_id, req.claim_id, req.question)
    except (ValueError, DebtBlockError, UngrilledError, KilledClaimError, ParkIsolationViolation) as exc:
        raise _handle_domain_error(exc)
    return {"event": event.model_dump(mode="json")}


@router.post("/grill/{artifact_id}/answer")
def grill_answer(
    artifact_id: str,
    req: AnswerRequest,
    grill_svc: GrillService = Depends(get_grill_service),
):
    try:
        event = grill_svc.answer(artifact_id, req.claim_id, req.response)
    except (ValueError, DebtBlockError, UngrilledError, KilledClaimError, ParkIsolationViolation) as exc:
        raise _handle_domain_error(exc)
    return {"event": event.model_dump(mode="json")}


@router.post("/grill/{artifact_id}/verdict")
def grill_verdict(
    artifact_id: str,
    req: VerdictRequest,
    grill_svc: GrillService = Depends(get_grill_service),
):
    try:
        event = grill_svc.verdict(
            artifact_id, req.claim_id, req.outcome, req.rationale,
        )
    except (ValueError, DebtBlockError, UngrilledError, KilledClaimError, ParkIsolationViolation) as exc:
        raise _handle_domain_error(exc)
    return {"event": event.model_dump(mode="json")}


@router.post("/grill/{artifact_id}/bypass")
def grill_bypass(
    artifact_id: str,
    req: BypassRequest,
    grill_svc: GrillService = Depends(get_grill_service),
):
    try:
        event = grill_svc.bypass(artifact_id, req.claim_id)
    except (ValueError, DebtBlockError, UngrilledError, KilledClaimError, ParkIsolationViolation) as exc:
        raise _handle_domain_error(exc)
    return {"event": event.model_dump(mode="json")}


@router.post("/grill/{artifact_id}/auto-challenge")
def auto_challenge(
    artifact_id: str,
    req: AutoChallengeRequest,
    grill_svc: GrillService = Depends(get_grill_service),
):
    try:
        event = grill_svc.auto_challenge(artifact_id, req.claim_id, req.claim_body, req.context)
        return {"event": event.model_dump(mode="json")}
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except LLMResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except (ValueError, DebtBlockError, UngrilledError, KilledClaimError, ParkIsolationViolation) as exc:
        raise _handle_domain_error(exc)


@router.post("/grill/{artifact_id}/auto-verdict")
def auto_verdict(
    artifact_id: str,
    req: AutoVerdictRequest,
    grill_svc: GrillService = Depends(get_grill_service),
):
    try:
        event = grill_svc.auto_verdict(
            artifact_id, req.claim_id, req.claim_body, req.question, req.answer,
        )
        return {"event": event.model_dump(mode="json")}
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except LLMResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except (ValueError, DebtBlockError, UngrilledError, KilledClaimError, ParkIsolationViolation) as exc:
        raise _handle_domain_error(exc)


# ---------------------------------------------------------------------------
# Promote endpoint
# ---------------------------------------------------------------------------


@router.post("/promote/{artifact_id}/{claim_id}")
def promote(
    artifact_id: str,
    claim_id: str,
    promote_svc: PromoteService = Depends(get_promote_service),
):
    try:
        event = promote_svc.promote(artifact_id, claim_id)
    except (DebtBlockError, UngrilledError, KilledClaimError, ValueError) as exc:
        raise _handle_domain_error(exc)
    return {"event": event.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Event (confirmation gate) endpoints
# ---------------------------------------------------------------------------


@router.post("/events/{artifact_id}/confirm")
def confirm_event(
    artifact_id: str,
    req: ConfirmRequest,
    event_svc: EventService = Depends(get_event_service),
):
    try:
        event = event_svc.confirm_event(artifact_id, req.event_id)
    except (ValueError,) as exc:
        raise _handle_domain_error(exc)
    return {"event": event.model_dump(mode="json")}


@router.post("/events/{artifact_id}/batch-confirm")
def batch_confirm(
    artifact_id: str,
    req: BatchConfirmRequest,
    event_svc: EventService = Depends(get_event_service),
):
    try:
        events = event_svc.batch_confirm(artifact_id, req.event_ids)
    except (ValueError,) as exc:
        raise _handle_domain_error(exc)
    return {"events": [e.model_dump(mode="json") for e in events]}


@router.post("/events/{artifact_id}/retract")
def retract_event(
    artifact_id: str,
    req: RetractRequest,
    event_svc: EventService = Depends(get_event_service),
):
    try:
        event = event_svc.retract_event(artifact_id, req.event_id)
    except (ValueError,) as exc:
        raise _handle_domain_error(exc)
    return {"event": event.model_dump(mode="json")}


@router.get("/events/{artifact_id}/pending")
def pending_events(
    artifact_id: str,
    event_svc: EventService = Depends(get_event_service),
):
    events = event_svc.pending_events(artifact_id)
    return {"events": [e.model_dump(mode="json") for e in events]}


# ---------------------------------------------------------------------------
# Projection (read-only) endpoints
# ---------------------------------------------------------------------------


@router.get("/artifact/{artifact_id}/doc")
def get_doc(
    artifact_id: str,
    promote_svc: PromoteService = Depends(get_promote_service),
):
    doc = promote_svc.get_doc(artifact_id)
    return {"events": [e.model_dump(mode="json") for e in doc]}


@router.get("/artifact/{artifact_id}/trajectory")
def get_trajectory(
    artifact_id: str,
    store: EventStore = Depends(get_event_store),
):
    events = store.get_events(artifact_id)
    return {"events": [e.model_dump(mode="json") for e in events]}


@router.get("/artifact/{artifact_id}/lens-feed")
def get_lens_feed_projection(
    artifact_id: str,
    store: EventStore = Depends(get_event_store),
):
    from anneal.domain.projections import lens_feed_projection

    events = store.get_events(artifact_id)
    feed = lens_feed_projection(events)
    return {"events": [e.model_dump(mode="json") for e in feed]}


# ---------------------------------------------------------------------------
# Lens feed endpoints
# ---------------------------------------------------------------------------


@router.post("/lens-feed/{artifact_id}")
def ingest_lens_feed(
    artifact_id: str,
    req: LensFeedIngestRequest,
    lens_svc: LensFeedService = Depends(get_lens_feed_service),
):
    try:
        entries = lens_svc.ingest(artifact_id, req.library_id)
    except (ValueError, DebtBlockError, UngrilledError, KilledClaimError, ParkIsolationViolation) as exc:
        raise _handle_domain_error(exc)
    return {"entries": [e.model_dump(mode="json") for e in entries]}


@router.get("/lens-feed")
def query_lens_feed(
    library_id: str,
    lens_svc: LensFeedService = Depends(get_lens_feed_service),
):
    entries = lens_svc.query_feed(library_id)
    return {"entries": [e.model_dump(mode="json") for e in entries]}
