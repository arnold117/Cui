"""Semantic Scholar search adapter — pure fetcher, neutral dict contract.

S2 Graph API (``https://api.semanticscholar.org/graph/v1/paper/search``) works
keyless at a much lower (aggressively rate-limited) rate. To survive the keyless
limit ``search_semantic_scholar`` implements **exponential backoff** — mirroring
``arxiv.py`` exactly: on a 429/503 status or a transient request error it retries
up to 3 times with delays of 1s, 2s, 4s (via ``asyncio.sleep``). On exhausting
the retries, or on any other HTTP error / timeout / malformed JSON, it degrades
gracefully to ``[]``.

An optional ``S2_API_KEY`` (read from the environment) lifts the rate limit when
present; it is sent as the ``x-api-key`` header. Unset -> keyless, as before.

No domain imports, no module-global mutable state. ``map_semantic_scholar`` is a
pure helper so tests/fixtures map without an HTTP round-trip.
"""

from __future__ import annotations

import asyncio
import logging
import os

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
TIMEOUT_SECONDS = 15.0
FIELDS = "title,abstract,year,venue,citationCount,externalIds,authors,openAccessPdf"

# Exponential backoff for S2's aggressive (keyless) rate limiting.
MAX_RETRIES = 3
BACKOFF_DELAYS = (1.0, 2.0, 4.0)  # seconds; index by (attempt - 1)
RETRY_STATUSES = frozenset({429, 503})


def _load_api_key() -> str | None:
    """Read the optional Semantic Scholar API key from env. None if unset.

    When present it lifts the keyless rate limit; sent as the ``x-api-key``
    header. Mirrors the ``load_dotenv()`` + ``os.getenv`` pattern used by
    ``collect_service._load_contact_email``.
    """
    load_dotenv()
    return os.getenv("S2_API_KEY") or None


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

    Retries with exponential backoff (1s, 2s, 4s) on 429/503 or transient
    request errors, up to ``MAX_RETRIES`` times. Returns ``[]`` on exhausted
    retries or any other HTTP error / timeout / malformed JSON. 15s timeout.

    If ``S2_API_KEY`` is set in the environment it is sent as ``x-api-key`` to
    lift the keyless rate limit; otherwise the call is keyless.
    """
    params: dict[str, object] = {
        "query": query,
        "limit": min(max(max_results, 1), 100),
        "fields": FIELDS,
    }

    api_key = _load_api_key()
    headers: dict[str, str] = {"x-api-key": api_key} if api_key else {}

    data: dict | None = None
    attempt = 0
    while True:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                response = await client.get(BASE_URL, params=params, headers=headers)
                if response.status_code in RETRY_STATUSES:
                    if attempt < MAX_RETRIES:
                        delay = BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS) - 1)]
                        logger.warning(
                            "Semantic Scholar %s for %r; backing off %.0fs "
                            "(attempt %d/%d)",
                            response.status_code, query, delay, attempt + 1, MAX_RETRIES,
                        )
                        await asyncio.sleep(delay)
                        attempt += 1
                        continue
                    logger.warning(
                        "Semantic Scholar retries exhausted for %r", query
                    )
                    return []
                response.raise_for_status()
                data = response.json()
                break
        except httpx.TransportError as exc:
            # Connection/timeout errors are transient -> back off and retry.
            if attempt < MAX_RETRIES:
                delay = BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS) - 1)]
                logger.warning(
                    "Semantic Scholar transient error for %r: %s; backing off "
                    "%.0fs (attempt %d/%d)",
                    query, exc, delay, attempt + 1, MAX_RETRIES,
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue
            logger.warning(
                "Semantic Scholar retries exhausted (transport) for %r", query
            )
            return []
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Semantic Scholar search failed for %r: %s", query, exc)
            return []

    if data is None:
        return []

    results = data.get("data") or []
    papers: list[dict] = []
    for raw in results:
        papers.append(map_semantic_scholar(raw))
        if len(papers) >= max_results:
            break
    return papers
