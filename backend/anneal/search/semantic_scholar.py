"""Semantic Scholar search adapter — pure fetcher, neutral dict contract.

S2 Graph API (``https://api.semanticscholar.org/graph/v1/paper/search``) works
keyless at a lower rate limit. On any HTTP error / timeout / malformed JSON we
degrade gracefully to ``[]``.

No domain imports, no module-global mutable state. ``map_semantic_scholar`` is a
pure helper so tests/fixtures map without an HTTP round-trip.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
TIMEOUT_SECONDS = 15.0
FIELDS = "title,abstract,year,venue,citationCount,externalIds,authors,openAccessPdf"


def map_semantic_scholar(paper: dict) -> dict:
    """Map one S2 paper dict -> the neutral paper-like dict. Pure."""
    external_ids = paper.get("externalIds") or {}
    open_access = paper.get("openAccessPdf") or {}

    authors = [
        (a.get("name") or "")
        for a in (paper.get("authors") or [])
    ]
    authors = [name for name in authors if name]

    year = paper.get("year")
    year = year if isinstance(year, int) else None

    citations = paper.get("citationCount")
    citations = citations if isinstance(citations, int) else 0

    pdf_urls: list[str] = []
    if open_access.get("url"):
        pdf_urls.append(open_access["url"])

    doi = external_ids.get("DOI") or ""
    source_id = paper.get("paperId") or ""

    return {
        "source": "semantic_scholar",
        "source_id": source_id,
        "title": paper.get("title") or "",
        "authors": authors,
        "abstract": paper.get("abstract") or "",
        "year": year,
        "venue": paper.get("venue") or "",
        "citations": citations,
        "doi": doi,
        "pdf_urls": pdf_urls,
        "url": paper.get("url") or (
            f"https://www.semanticscholar.org/paper/{source_id}" if source_id else ""
        ),
    }


async def search_semantic_scholar(
    query: str,
    max_results: int = 10,
    **_kw,
) -> list[dict]:
    """Search Semantic Scholar; return neutral paper-like dicts.

    Graceful degradation: returns ``[]`` on HTTP error / timeout / malformed
    response instead of raising. 15s timeout.
    """
    params: dict[str, object] = {
        "query": query,
        "limit": min(max(max_results, 1), 100),
        "fields": FIELDS,
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.get(BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Semantic Scholar search failed for %r: %s", query, exc)
        return []

    results = data.get("data") or []
    papers: list[dict] = []
    for raw in results:
        papers.append(map_semantic_scholar(raw))
        if len(papers) >= max_results:
            break
    return papers
