"""Native corpus search (slice1 S1.1): read-only IDF-ranked search over the
imported v4 corpus materials (active workspace by default).

Layering: this router is host code — it reads the native store (SDK types) and
scores with the pure CJK+IDF ranking ported in ``cui.legacy_archive.search``
(kernel purity untouched; legacy_archive is never imported by the kernel/SDK).
Search scope mirrors the corpus partition: the deterministic v4 corpus
workspaces (``cui.tools.v4_importer`` constants) carry the materials.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from cui.legacy_archive.search.ranking import extract_core_terms, rank_by_idf
from cui.research_universe.api.routes import LibraryContext
from cui.research_universe.api.slice1 import _active
from cui.tools.v4_importer import ACTIVE_WS_COMMAND, LEGACY_WS_COMMAND, first_title, workspace_id_for


class CorpusSearchHit(BaseModel):
    material_id: str
    source_locator: str
    title: str
    matched_terms: int
    snippet: str


class CorpusSearchResponse(BaseModel):
    query: str
    group: str
    total: int
    results: list[CorpusSearchHit]


def _corpus_materials(store, universe_id: str, workspace_id: str) -> list[dict]:
    """material_added payloads in the given corpus workspace (evidence, parsed)."""
    materials = []
    for event in store.read_events(universe_id):
        if event.event_type != "material_added":
            continue
        payload = event.validated_payload()
        if payload.workspace_id != workspace_id:
            continue
        if payload.purpose != "evidence" or payload.parse_status != "parsed":
            continue
        materials.append(payload.model_dump())
    return materials


def create_corpus_search_router(store, context: LibraryContext) -> APIRouter:
    router = APIRouter(tags=["research-universe-corpus-search"])

    @router.get("/corpus/search", response_model=CorpusSearchResponse)
    def search(
        q: str = Query(min_length=1, max_length=200),
        group: Literal["active", "legacy"] = "active",
        limit: int = Query(default=20, ge=1, le=50),
    ) -> CorpusSearchResponse:
        universe_id = _active(store, context)
        if not q.strip():
            raise HTTPException(422, "q must not be blank")
        workspace_id = workspace_id_for(ACTIVE_WS_COMMAND if group == "active" else LEGACY_WS_COMMAND)
        materials = _corpus_materials(store, universe_id, workspace_id)
        if not materials:
            return CorpusSearchResponse(query=q, group=group, total=0, results=[])
        texts = [(first_title(m["excerpt"]), m["excerpt"]) for m in materials]
        terms = extract_core_terms([q])
        if not terms:
            # Pure CJK / phrase queries: fall back to a single raw substring term
            # (Chinese texts match on the whole phrase, mirroring the v4 routing
            # intent that CJK never tokenizes against English sources).
            terms = [q.lower()]
        order = rank_by_idf(texts, terms)
        hits = []
        for index in order[:limit]:
            material = materials[index]
            excerpt = material["excerpt"]
            matched = sum(1 for t in terms if t in f"{texts[index][0]} {excerpt}".lower())
            if matched == 0:
                continue
            snippet = " ".join(excerpt.split())[:300]
            hits.append(CorpusSearchHit(
                material_id=material["material_id"],
                source_locator=material["source_locator"],
                title=texts[index][0],
                matched_terms=matched,
                snippet=snippet,
            ))
        return CorpusSearchResponse(query=q, group=group, total=len(materials), results=hits)

    return router
