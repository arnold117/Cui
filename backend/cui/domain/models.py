from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class Library(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Project(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    library_id: str
    goal: str


class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    library_id: str
    project_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Claim(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    library_id: str
    body: str
    artifact_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Material(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    library_id: str
    kind: str
    provenance: dict = Field(default_factory=dict)
    payload: dict = Field(default_factory=dict)


class Artifact(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    library_id: str
    kind: str
    goal: str
    constraints: list[dict] = Field(default_factory=list)
    project_ids: list[str] = Field(default_factory=list)
    material_ids: list[str] = Field(default_factory=list)
    title: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
