"""CrossRef search adapter — pure fetcher, neutral dict contract.

CrossRef (``https://api.crossref.org/works``) needs no API key. Passing
``mailto`` opts into the "polite pool" for better rate limits. On any HTTP
error / timeout / malformed JSON we degrade gracefully to ``[]``.

No domain imports, no module-global mutable state. ``map_crossref`` is a pure
helper so tests/fixtures map without an HTTP round-trip.
"""

from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.crossref.org/works"
TIMEOUT_SECONDS = 15.0

_JATS_TAG = re.compile(r"<[^>]+>")


def _strip_jats(text: str) -> str:
    """Strip JATS/XML/HTML tags from a CrossRef abstract. Pure."""
    if not text:
        return ""
    return _JATS_TAG.sub("", text).strip()


def map_crossref(item: dict) -> dict:
    """Map one CrossRef work item -> the neutral paper-like dict. Pure."""
    title_list = item.get("title") or []
    title = title_list[0] if title_list else ""

    authors: list[str] = []
    for a in item.get("author") or []:
        name = f"{a.get('given', '')} {a.get('family', '')}".strip()
        if name:
            authors.append(name)

    # Year: prefer published, then published-print/online, then issued.
    year: int | None = None
    for key in ("published", "published-print", "published-online", "issued"):
        parts = ((item.get(key) or {}).get("date-parts") or [[]])
        if parts and parts[0]:
            candidate = parts[0][0]
            if isinstance(candidate, int):
                year = candidate
                break

    venue_list = item.get("container-title") or []
    venue = venue_list[0] if venue_list else ""

    doi = item.get("DOI") or ""

    citations = item.get("is-referenced-by-count")
    citations = citations if isinstance(citations, int) else 0

    url = item.get("URL") or (f"https://doi.org/{doi}" if doi else "")

    return {
        "source": "crossref",
        "source_id": doi,
        "title": title,
        "authors": authors,
        "abstract": _strip_jats(item.get("abstract") or ""),
        "year": year,
        "venue": venue,
        "citations": citations,
        "doi": doi,
        "pdf_urls": [],
        "url": url,
    }


async def search_crossref(
    query: str,
    max_results: int = 10,
    mailto: str | None = None,
    **_kw,
) -> list[dict]:
    """Search CrossRef works; return neutral paper-like dicts.

    Graceful degradation: returns ``[]`` on HTTP error / timeout / malformed
    response instead of raising. 15s timeout.
    """
    params: dict[str, object] = {
        "query": query,
        "rows": min(max(max_results, 1), 1000),
    }
    if mailto:
        params["mailto"] = mailto

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.get(BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("CrossRef search failed for %r: %s", query, exc)
        return []

    items = (data.get("message") or {}).get("items") or []
    papers: list[dict] = []
    for item in items:
        papers.append(map_crossref(item))
        if len(papers) >= max_results:
            break
    return papers
