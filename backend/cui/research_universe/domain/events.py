"""Typed native Research Universe events and Slice 1 catalogue."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, TypeAlias
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class ParkReleasedPayload(Payload):
    release_id: str
    capture_id: str
    workspace_id: str
    provisional_role: Literal["trigger_question", "exploration_context", "material_lead", "unnamed"]


class ClaimForgedFromCapturePayload(Payload):
    provenance_id: str
    claim_id: str
    capture_id: str
    release_id: str
    workspace_id: str
    author: Literal["user"] = "user"


class ChallengeAnsweredPayload(Payload):
    challenge_id: str
    round_id: str
    claim_id: str
    answer_version_id: str
    answer_text: str = Field(min_length=1)
    author: Literal["user"] = "user"
    provisional_anchor_refs: list[str] = Field(default_factory=list)


class ChallengeDeferredPayload(Payload):
    challenge_id: str
    round_id: str
    claim_id: str
    reason: str = Field(min_length=1)
    condition: str = Field(min_length=1)


class ChallengeWithdrawnPayload(Payload):
    challenge_id: str
    round_id: str
    claim_id: str
    reason: str = Field(min_length=1)


class VerdictConfirmedPayload(Payload):
    round_id: str
    workspace_id: str
    claim_id: str
    verdict_type: Literal["survived", "refuted", "not_worth", "boundary", "circumstantial"]
    user_reason: str = Field(min_length=1)
    revival_condition: str | None = None

    @model_validator(mode="after")
    def _revival_condition_rule(self) -> "VerdictConfirmedPayload":
        if self.verdict_type == "circumstantial":
            if not self.revival_condition or not self.revival_condition.strip():
                raise ValueError("circumstantial verdict requires a non-empty revival_condition")
        elif self.revival_condition is not None:
            raise ValueError("revival_condition is only valid for circumstantial verdicts")
        return self


class MaterialAddedPayload(Payload):
    material_id: str
    workspace_id: str
    excerpt: str = Field(min_length=1)
    source_locator: str | None = None
    parse_status: Literal["parsed", "failed"]
    purpose: Literal["evidence", "reference"]
    author: Literal["user"] = "user"


class EvidenceRelationProposedPayload(Payload):
    candidate_id: str
    round_id: str
    workspace_id: str
    claim_id: str
    claim_version_id: str
    claim_text: str
    material_id: str
    material_excerpt: str
    material_source_locator: str | None = None
    relation: Literal["supports", "contradicts", "silent", "cannot_assess"]
    uncertainty: str | None = None
    generator_kind: Literal["user", "system"] = "user"
    prompt_version: str | None = None
    model_identifier: str | None = None
    basis_refs: list[str] = Field(default_factory=list)
    # Slice 6: LLM-generated candidates carry the model's 为何 (rationale) and
    # 证据高亮 (evidence_highlight).  Optional so Slice 4 stored events (without
    # these fields) still validate; schema version is intentionally NOT bumped.
    rationale: str | None = None
    evidence_highlight: str | None = None
    author: Literal["user"] = "user"


class EvidenceRelationConfirmedPayload(Payload):
    candidate_id: str
    round_id: str
    claim_id: str
    relation: Literal["supports", "contradicts", "silent", "cannot_assess"]
    user_reason: str | None = None


class EvidenceRelationCorrectedPayload(Payload):
    candidate_id: str
    round_id: str
    claim_id: str
    prior_relation: Literal["supports", "contradicts", "silent", "cannot_assess"]
    corrected_relation: Literal["supports", "contradicts", "silent", "cannot_assess"]
    user_reason: str | None = None


class EvidenceRelationRejectedPayload(Payload):
    candidate_id: str
    round_id: str
    claim_id: str
    user_reason: str | None = None


class EvidenceRelationWithdrawnPayload(Payload):
    candidate_id: str
    round_id: str
    claim_id: str
    user_reason: str | None = None


# --- Slice 5: workspace crystallization / direction impact --------------------

WorkspacePosition: TypeAlias = Literal["exploring", "paused", "concluded", "branched", "absorbed"]
ConclusionType: TypeAlias = Literal["tentative_answer", "negated_path", "boundary", "key_unknown", "deferred", "split_or_turn"]


class WorkspacePausedPayload(Payload):
    workspace_id: str
    user_reason: str | None = None


class WorkspaceReopenedPayload(Payload):
    workspace_id: str
    user_reason: str | None = None


class WorkspaceConcludedPayload(Payload):
    workspace_id: str
    conclusion_id: str
    conclusion_type: ConclusionType
    conclusion_text: str = Field(min_length=1)
    user_reason: str | None = None
    basis_refs: list[str] = Field(default_factory=list)
    revival_condition: str | None = None
    new_user_position: Literal["concluded"] = "concluded"

    @model_validator(mode="after")
    def _revival_condition_rule(self) -> "WorkspaceConcludedPayload":
        if self.conclusion_type == "deferred":
            if not self.revival_condition or not self.revival_condition.strip():
                raise ValueError("deferred conclusion requires a non-empty revival_condition")
        elif self.revival_condition is not None:
            raise ValueError("revival_condition is only valid for deferred conclusions")
        return self


class WorkspaceBranchedPayload(Payload):
    workspace_id: str
    successor_workspace_id: str
    user_reason: str = Field(min_length=1)
    new_user_position: Literal["branched"] = "branched"


class WorkspaceAbsorbedPayload(Payload):
    workspace_id: str
    target_workspace_id: str
    user_reason: str = Field(min_length=1)
    new_user_position: Literal["absorbed"] = "absorbed"


class DirectionCreatedPayload(Payload):
    direction_id: str
    proposition_version_id: str
    proposition_text: str = Field(min_length=1)
    declared_status: Literal["active"] = "active"
    author: Literal["user"] = "user"


class DirectionStatusDeclaredPayload(Payload):
    direction_id: str
    status: Literal["active", "on_hold", "retired"]
    user_reason: str = Field(min_length=1)


class DirectionPropositionRephrasedPayload(Payload):
    direction_id: str
    prior_proposition_version_id: str
    prior_proposition_text: str
    new_proposition_version_id: str
    new_proposition_text: str | None = None
    change_type: Literal["clarify", "narrow_or_widen", "turning", "unnamed"]
    user_reason: str = Field(min_length=1)
    source_conclusion_ref: str | None = None

    @model_validator(mode="after")
    def _unnamed_rule(self) -> "DirectionPropositionRephrasedPayload":
        if self.change_type == "unnamed":
            if self.new_proposition_text is not None:
                raise ValueError("unnamed rephrase must carry an explicit null proposition")
        elif not self.new_proposition_text or not self.new_proposition_text.strip():
            raise ValueError("non-unnamed rephrase requires a non-empty proposition")
        return self


class WorkspaceDirectionAttachedPayload(Payload):
    direction_link_id: str
    workspace_id: str
    direction_id: str
    user_reason: str | None = None


class WorkspaceDirectionDetachedPayload(Payload):
    direction_link_id: str
    workspace_id: str
    direction_id: str
    user_reason: str | None = None


class WorkspaceCrystallizationAttachedPayload(Payload):
    crystallization_id: str
    direction_id: str
    workspace_id: str
    conclusion_id: str
    conclusion_text: str
    conclusion_type: ConclusionType
    user_reason: str | None = None


Slice1Payload: TypeAlias = Annotated[
    WorkspaceCreatedPayload
    | ExplorationNoteSavedPayload
    | ExplorationAnchorCreatedPayload
    | ClaimCreatedPayload
    | ReviewRoundStartedPayload
    | ChallengeCreatedPayload
    | ParkReleasedPayload
    | ClaimForgedFromCapturePayload,
    Field(discriminator=None),
]

EVENT_PAYLOAD_TYPES: dict[tuple[str, int], type[Payload]] = {
    ("workspace_created", 1): WorkspaceCreatedPayload,
    ("exploration_note_saved", 1): ExplorationNoteSavedPayload,
    ("exploration_anchor_created", 1): ExplorationAnchorCreatedPayload,
    ("claim_created", 1): ClaimCreatedPayload,
    ("review_round_started", 1): ReviewRoundStartedPayload,
    ("challenge_created", 1): ChallengeCreatedPayload,
    ("park_released", 1): ParkReleasedPayload,
    ("claim_forged_from_capture", 1): ClaimForgedFromCapturePayload,
    ("challenge_answered", 1): ChallengeAnsweredPayload,
    ("challenge_deferred", 1): ChallengeDeferredPayload,
    ("challenge_withdrawn", 1): ChallengeWithdrawnPayload,
    ("verdict_confirmed", 1): VerdictConfirmedPayload,
    ("material_added", 1): MaterialAddedPayload,
    ("evidence_relation_proposed", 1): EvidenceRelationProposedPayload,
    ("evidence_relation_confirmed", 1): EvidenceRelationConfirmedPayload,
    ("evidence_relation_corrected", 1): EvidenceRelationCorrectedPayload,
    ("evidence_relation_rejected", 1): EvidenceRelationRejectedPayload,
    ("evidence_relation_withdrawn", 1): EvidenceRelationWithdrawnPayload,
    ("workspace_paused", 1): WorkspacePausedPayload,
    ("workspace_reopened", 1): WorkspaceReopenedPayload,
    ("workspace_concluded", 1): WorkspaceConcludedPayload,
    ("workspace_branched", 1): WorkspaceBranchedPayload,
    ("workspace_absorbed", 1): WorkspaceAbsorbedPayload,
    ("direction_created", 1): DirectionCreatedPayload,
    ("direction_status_declared", 1): DirectionStatusDeclaredPayload,
    ("direction_proposition_rephrased", 1): DirectionPropositionRephrasedPayload,
    ("workspace_direction_attached", 1): WorkspaceDirectionAttachedPayload,
    ("workspace_direction_detached", 1): WorkspaceDirectionDetachedPayload,
    ("workspace_crystallization_attached", 1): WorkspaceCrystallizationAttachedPayload,
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
