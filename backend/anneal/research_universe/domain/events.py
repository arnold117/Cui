"""Typed native Research Universe events and Slice 1 catalogue."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, TypeAlias
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WorkspaceCreatedPayload(Payload):
    workspace_id: str
    initial_question_version_id: str
    initial_question_text: str
    user_position: Literal["exploring"] = "exploring"


class ExplorationNoteSavedPayload(Payload):
    note_id: str
    note_revision_id: str
    workspace_id: str
    text: str
    author: Literal["user"] = "user"


class ExplorationAnchorCreatedPayload(Payload):
    anchor_id: str
    workspace_id: str
    note_id: str
    note_revision_id: str
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    selected_text: str
    author: Literal["user"] = "user"


class ClaimCreatedPayload(Payload):
    claim_id: str
    origin_workspace_id: str
    claim_version_id: str
    claim_text: str
    author: Literal["user"] = "user"


class ReviewRoundStartedPayload(Payload):
    round_id: str
    workspace_id: str
    question_version_id: str
    question_text: str
    claim_id: str
    claim_version_id: str
    claim_text: str


class ChallengeCreatedPayload(Payload):
    challenge_id: str
    round_id: str
    claim_id: str
    claim_version_id: str
    claim_text: str
    attack_surface: str
    why_it_matters: str
    self_check_method: str
    generator_kind: Literal["system", "user"]
    prompt_version: str
    model_identifier: str | None
    basis_refs: list[str]
    uncertainty: str


Slice1Payload: TypeAlias = Annotated[
    WorkspaceCreatedPayload
    | ExplorationNoteSavedPayload
    | ExplorationAnchorCreatedPayload
    | ClaimCreatedPayload
    | ReviewRoundStartedPayload
    | ChallengeCreatedPayload,
    Field(discriminator=None),
]

EVENT_PAYLOAD_TYPES: dict[tuple[str, int], type[Payload]] = {
    ("workspace_created", 1): WorkspaceCreatedPayload,
    ("exploration_note_saved", 1): ExplorationNoteSavedPayload,
    ("exploration_anchor_created", 1): ExplorationAnchorCreatedPayload,
    ("claim_created", 1): ClaimCreatedPayload,
    ("review_round_started", 1): ReviewRoundStartedPayload,
    ("challenge_created", 1): ChallengeCreatedPayload,
}


def validate_payload(event_type: str, schema_version: int, payload: dict[str, object]) -> Payload:
    """Validate an admitted event against its explicit catalogue version."""
    try:
        payload_type = EVENT_PAYLOAD_TYPES[(event_type, schema_version)]
    except KeyError as exc:
        raise ValueError(f"event type/version is not in the native catalogue: {event_type}@v{schema_version}") from exc
    return payload_type.model_validate(payload)


class NativeEvent(BaseModel):
    """Fully-addressed, replay-orderable native event envelope."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    universe_id: str
    aggregate_type: str
    aggregate_id: str
    stream_id: str
    sequence: int
    commit_position: int
    commit_index: int
    event_type: str
    actor_kind: Literal["user", "system"]
    actor_id: str | None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, object]
    causation_id: str | None = None
    correlation_id: str | None = None
    schema_version: int = 1

    def validated_payload(self) -> BaseModel:
        return validate_payload(self.event_type, self.schema_version, self.payload)


class PendingNativeEvent(BaseModel):
    """An event before stream and durable commit coordinates are assigned."""

    model_config = ConfigDict(frozen=True)

    event_type: str
    payload: dict[str, object]
    aggregate_type: str
    aggregate_id: str
    causation_id: str | None = None
    correlation_id: str | None = None
    schema_version: int = 1

    def validated_payload(self) -> BaseModel:
        return validate_payload(self.event_type, self.schema_version, self.payload)
