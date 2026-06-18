"""Collect service — fetches literature and maps it into native Materials.

Stage 1 of the literature-search slice. Mirrors ``ParkService``'s shape:
constructor ``(store, event_service, repo)``; a method creates domain entities,
persists them via ``self._repo.create_*``, and appends events via
``self._event_service.append_event``.

The fetcher (``anneal.search.openalex``) returns neutral paper-like dicts;
this native service is the only place that knows about the ``Material`` model.
Collecting a paper is a *factual fetch*, so its event is ``confirmed=True`` —
the grounding judgment (Stage 2) is what will be pending.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from anneal.domain.events import COLLECT_MATERIAL, make_event
from anneal.domain.models import Material
from anneal.search.multi import search_all
from anneal.services.event_service import EventService
from anneal.store.event_store import EventStore
from anneal.store.repository import Repository


def _load_contact_email() -> str | None:
    """Read the polite-pool contact email from env. None if unset.

    Used as ``mailto`` for OpenAlex and CrossRef polite pools.
    """
    load_dotenv()
    return os.getenv("OPENALEX_CONTACT") or None


class CollectService:
    """Fetches papers from a search source and persists them as Materials."""

    def __init__(
        self, store: EventStore, event_service: EventService, repo: Repository
    ) -> None:
        self._store = store
        self._event_service = event_service
        self._repo = repo

    async def collect(
        self,
        artifact_id: str,
        library_id: str,
        query: str,
        max_results: int = 10,
        sources: list[str] | None = None,
    ) -> list[Material]:
        """Search all sources, persist each deduped hit, log COLLECT events.

        - Calls ``search_all`` (multi-source + dedupe) with the configured
          polite-pool contact; ``sources=None`` searches every source.
        - Builds a native ``Material(kind="paper")`` per *deduped* result with
          provenance (source/source_id/doi/url/query/sources) and payload
          (title/authors/abstract/year/venue/citations/pdf_urls). The merged
          ``sources`` list from dedupe is persisted into provenance.
        - Persists each via ``repo.create_material``.
        - Appends one ``collect_material`` event per material (confirmed=True)
          targeting the material id, on the *artifact*'s event stream.
        - Returns the created Material objects (empty list if the search
          degraded to no results).
        """
        results = await search_all(
            query,
            sources=sources,
            max_per_source=max_results,
            mailto=_load_contact_email(),
        )

        materials: list[Material] = []
        for paper in results:
            material = Material(
                library_id=library_id,
                kind="paper",
                provenance={
                    "source": paper["source"],
                    "source_id": paper["source_id"],
                    "doi": paper["doi"],
                    "url": paper["url"],
                    "query": query,
                    "sources": paper.get("sources", [paper["source"]]),
                },
                payload={
                    "title": paper["title"],
                    "authors": paper["authors"],
                    "abstract": paper["abstract"],
                    "year": paper["year"],
                    "venue": paper["venue"],
                    "citations": paper["citations"],
                    "pdf_urls": paper["pdf_urls"],
                },
            )
            self._repo.create_material(material)

            event = make_event(
                type=COLLECT_MATERIAL,
                actor="system",
                confirmed=True,
                target_ref=material.id,
                payload={
                    "material_id": material.id,
                    "source": paper["source"],
                    "title": paper["title"],
                    "query": query,
                },
            )
            self._event_service.append_event(artifact_id, event)

            materials.append(material)

        return materials
