"""Minimal Slice 0 native endpoints: server-scoped active universe only."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from anneal.research_universe.store.event_store import NativeEventStore, UniverseAlreadyActive


@dataclass(frozen=True)
class LibraryContext:
    library_id: str


@dataclass(frozen=True)
class LocalPrincipal:
    kind: str = "user"
    id: str | None = "local"


class UniverseResponse(BaseModel):
    id: str
    library_id: str


def create_router(store: NativeEventStore, library_context: LibraryContext, principal: LocalPrincipal) -> APIRouter:
    router = APIRouter(prefix="/universes", tags=["research-universe"])

    def active_library() -> LibraryContext:
        return library_context

    @router.get("/active", response_model=UniverseResponse)
    def get_active(context: LibraryContext = Depends(active_library)) -> UniverseResponse:
        universe_id = store.get_active_universe(context.library_id)
        if universe_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no active universe")
        return UniverseResponse(id=universe_id, library_id=context.library_id)

    @router.post("", response_model=UniverseResponse, status_code=status.HTTP_201_CREATED)
    def provision_active(context: LibraryContext = Depends(active_library)) -> UniverseResponse:
        existing = store.get_active_universe(context.library_id)
        if existing:
            return UniverseResponse(id=existing, library_id=context.library_id)
        try:
            universe_id = store.create_active_universe(context.library_id)
        except UniverseAlreadyActive:
            universe_id = store.get_active_universe(context.library_id)
            assert universe_id is not None
        return UniverseResponse(id=universe_id, library_id=context.library_id)

    return router
