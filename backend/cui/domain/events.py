from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

PARK = "park"
COLLECT_MATERIAL = "collect_material"
ANALYZE_MATERIAL = "analyze_material"
CHALLENGE = "challenge"
ANSWER = "answer"
VERDICT = "verdict"
GAP = "gap"
DRAFT = "draft"
CONSTRAIN = "constrain"
REVISE = "revise"
GROUND = "ground"
PROMOTE = "promote"
EDIT = "edit"
CONFIRM = "confirm"
RETRACT = "retract"
LINK = "link"

ALL_EVENT_TYPES = {
    PARK, COLLECT_MATERIAL, ANALYZE_MATERIAL, CHALLENGE, ANSWER, VERDICT,
    GAP, DRAFT, CONSTRAIN, REVISE, GROUND, PROMOTE, EDIT, CONFIRM, RETRACT,
    LINK,
}


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    ts: datetime = Field(default_factory=datetime.utcnow)
    type: str
    actor: str
    strictness: int | None = None
    debt: bool = False
    confirmed: bool = False
    target_ref: str | None = None
    payload: dict = Field(default_factory=dict)


def make_event(
    type: str,
    actor: str,
    payload: dict | None = None,
    debt: bool = False,
    confirmed: bool = False,
    strictness: int | None = None,
    target_ref: str | None = None,
) -> Event:
    return Event(
        type=type,
        actor=actor,
        payload=payload or {},
        debt=debt,
        confirmed=confirmed,
        strictness=strictness,
        target_ref=target_ref,
    )
