"""Multi-source search orchestrator.

Runs the selected source adapters concurrently, concatenates their neutral
paper-like dicts, and deduplicates the result. Each adapter must never sink the
whole search: any adapter raising is treated as ``[]``.

Adapters are looked up via a name -> callable registry, so adding a source
later (e.g. PubMed) is a one-line registry entry.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from anneal.search.arxiv import search_arxiv
from anneal.search.crossref import search_crossref
from anneal.search.dedupe import dedupe
from anneal.search.europe_pmc import search_europepmc
from anneal.search.openalex import search_openalex
from anneal.search.pubmed import search_pubmed
from anneal.search.semantic_scholar import search_semantic_scholar

logger = logging.getLogger(__name__)

Adapter = Callable[..., Awaitable[list[dict]]]

# name -> adapter callable. Extend here to register a new source.
REGISTRY: dict[str, Adapter] = {
    "openalex": search_openalex,
    "crossref": search_crossref,
    "europepmc": search_europepmc,
    "semantic_scholar": search_semantic_scholar,
    "arxiv": search_arxiv,
    "pubmed": search_pubmed,
}

DEFAULT_SOURCES: list[str] = [
    "openalex",
    "crossref",
    "europepmc",
    "semantic_scholar",
    "arxiv",
    "pubmed",
]


async def search_all(
    query: str,
    sources: list[str] | None = None,
    max_per_source: int = 10,
    mailto: str | None = None,
) -> list[dict]:
    """Search every selected source concurrently, then dedupe.

    - ``sources`` defaults to all registered sources. Unknown names are ignored.
    - Adapters run via ``asyncio.gather(..., return_exceptions=True)``; an
      adapter that raises contributes ``[]`` rather than failing the search.
    - ``mailto`` is forwarded to adapters that accept it (others ignore it via
      their ``**kw``).
    """
    selected = sources if sources is not None else DEFAULT_SOURCES

    tasks: list[Awaitable[list[dict]]] = []
    used_names: list[str] = []
    for name in selected:
        adapter = REGISTRY.get(name)
        if adapter is None:
            logger.warning("Unknown search source %r; skipping", name)
            continue
        tasks.append(adapter(query, max_results=max_per_source, mailto=mailto))
        used_names.append(name)

    if not tasks:
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)

    combined: list[dict] = []
    for name, result in zip(used_names, results):
        if isinstance(result, BaseException):
            logger.warning("Search source %r raised: %s", name, result)
            continue
        combined.extend(result)

    return dedupe(combined)
