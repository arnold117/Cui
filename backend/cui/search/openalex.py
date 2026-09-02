"""OpenAlex search adapter — pure fetcher, neutral dict contract.

Cherry-picked PURE logic (no domain imports, no global mutable state).
Returns a list of "paper-like" dicts with a fixed neutral schema; mapping to
the native ``Material`` model happens in the service layer, never here.

OpenAlex needs no API key. Passing ``mailto`` opts into the "polite pool"
for better rate limits. On any HTTP error / timeout we degrade gracefully
to ``[]`` rather than raising.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openalex.org"
TIMEOUT_SECONDS = 15.0


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    """Rebuild plaintext abstract from OpenAlex's inverted-index format.

    OpenAlex stores abstracts as ``{word: [pos1, pos2, ...]}`` for copyright
    reasons. We reorder words by position to recover the running text.

    Pure helper — no I/O. Returns "" for missing/empty input.
    """
    if not inverted_index:
        return ""
    positioned: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        for pos in positions:
            positioned.append((pos, word))
    positioned.sort(key=lambda pw: pw[0])
    return " ".join(word for _, word in positioned)


def _strip_prefix(value: str, prefix: str) -> str:
    return value[len(prefix):] if value.startswith(prefix) else value


def map_work(work: dict) -> dict:
    """Map one OpenAlex work object -> the neutral paper-like dict.

    Pure function — exposed separately so tests (and Stage 2) can map fixtures
    without an HTTP round-trip.
    """
    raw_id = work.get("id") or ""
    source_id = _strip_prefix(raw_id, "https://openalex.org/")

    doi = work.get("doi") or ""
    doi = _strip_prefix(doi, "https://doi.org/")

    authors = [
        (a.get("author") or {}).get("display_name") or ""
        for a in (work.get("authorships") or [])
    ]
    authors = [name for name in authors if name]

    primary = work.get("primary_location") or {}
    venue_source = primary.get("source") or {}
    venue = venue_source.get("display_name") or ""

    pdf_urls: list[str] = []
    for loc in work.get("locations") or []:
        pdf_url = loc.get("pdf_url")
        if pdf_url and pdf_url not in pdf_urls:
            pdf_urls.append(pdf_url)

    year = work.get("publication_year")
    year = year if isinstance(year, int) else None

    return {
        "source": "openalex",
        "source_id": source_id,
        "title": work.get("display_name") or work.get("title") or "",
        "authors": authors,
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "year": year,
        "venue": venue,
        "citations": work.get("cited_by_count") or 0,
        "doi": doi,
        "pdf_urls": pdf_urls,
        "url": raw_id,
    }


async def search_openalex(
    query: str,
    max_results: int = 10,
    mailto: str | None = None,
) -> list[dict]:
    """Search OpenAlex works; return neutral paper-like dicts.

    Graceful degradation: returns ``[]`` on HTTP error / timeout / malformed
    response instead of raising. 15s timeout.
    """
    params: dict[str, object] = {
        "search": query,
        "per_page": min(max(max_results, 1), 200),
    }
    if mailto:
        params["mailto"] = mailto

    url = f"{BASE_URL}/works"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        # httpx.HTTPError covers timeouts, connection errors, and HTTP status
        # errors; ValueError covers JSON decode failures.
        logger.warning("OpenAlex search failed for %r: %s", query, exc)
        return []

    results = data.get("results") or []
    papers: list[dict] = []
    for work in results:
        papers.append(map_work(work))
        if len(papers) >= max_results:
            break
    return papers
