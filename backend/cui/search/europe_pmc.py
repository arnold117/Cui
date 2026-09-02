"""Europe PMC search adapter — pure fetcher, neutral dict contract.

EuropePMC REST search (``https://www.ebi.ac.uk/europepmc/webservices/rest/search``)
needs no API key. On any HTTP error / timeout / malformed JSON we degrade
gracefully to ``[]``.

No domain imports, no module-global mutable state. ``map_europepmc`` is a pure
helper so tests/fixtures map without an HTTP round-trip.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
TIMEOUT_SECONDS = 15.0


def _parse_authors(author_str: str) -> list[str]:
    """Parse EuropePMC ``authorString`` (semicolon- or comma-separated). Pure."""
    if not author_str:
        return []
    sep = ";" if ";" in author_str else ","
    return [a.strip().rstrip(".") for a in author_str.split(sep) if a.strip()]


def map_europepmc(hit: dict) -> dict:
    """Map one EuropePMC result hit -> the neutral paper-like dict. Pure."""
    pmid = hit.get("pmid") or ""
    pmcid = hit.get("pmcid") or ""
    source_id = pmid or pmcid or (hit.get("id") or "")

    pdf_urls: list[str] = []
    if pmcid and hit.get("isOpenAccess") == "Y":
        pdf_urls.append(f"https://europepmc.org/articles/{pmcid}/pdf")

    venue = ""
    journal_info = hit.get("journalInfo") or {}
    if isinstance(journal_info, dict):
        journal = journal_info.get("journal") or {}
        venue = journal.get("title") or ""

    year: int | None = None
    raw_year = hit.get("pubYear")
    if raw_year:
        try:
            year = int(raw_year)
        except (TypeError, ValueError):
            year = None

    citations = hit.get("citedByCount")
    citations = citations if isinstance(citations, int) else 0

    doi = hit.get("doi") or ""

    # EuropePMC landing page.
    src = hit.get("source") or ""
    eid = hit.get("id") or ""
    url = (
        f"https://europepmc.org/article/{src}/{eid}"
        if src and eid
        else (f"https://doi.org/{doi}" if doi else "")
    )

    return {
        "source": "europepmc",
        "source_id": source_id,
        "title": hit.get("title") or "",
        "authors": _parse_authors(hit.get("authorString") or ""),
        "abstract": hit.get("abstractText") or "",
        "year": year,
        "venue": venue,
        "citations": citations,
        "doi": doi,
        "pdf_urls": pdf_urls,
        "url": url,
    }


async def search_europepmc(
    query: str,
    max_results: int = 10,
    **_kw,
) -> list[dict]:
    """Search EuropePMC; return neutral paper-like dicts.

    Graceful degradation: returns ``[]`` on HTTP error / timeout / malformed
    response instead of raising. 15s timeout.
    """
    params: dict[str, object] = {
        "query": query,
        "format": "json",
        "resultType": "core",
        "pageSize": min(max(max_results, 1), 100),
        # Note: do NOT pass sort= — it breaks the API (returns hitCount:None).
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.get(BASE_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("EuropePMC search failed for %r: %s", query, exc)
        return []

    results = (data.get("resultList") or {}).get("result") or []
    papers: list[dict] = []
    for hit in results:
        papers.append(map_europepmc(hit))
        if len(papers) >= max_results:
            break
    return papers
