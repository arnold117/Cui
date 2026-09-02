"""arXiv search adapter — pure fetcher, neutral dict contract.

Built natively against the arXiv Atom API (``https://export.arxiv.org/api/query``)
with ``httpx`` and stdlib ``xml.etree.ElementTree`` — no ``arxiv`` library, no
new dependency.

NOTE: arXiv 301-redirects http -> https. httpx does NOT follow redirects by
default, so we use the https URL *and* construct the client with
``follow_redirects=True`` (belt-and-suspenders for any future redirect).

arXiv rate-limits aggressively, so ``search_arxiv`` implements **exponential
backoff**: on a 429/503 status or a transient request error it retries up to
3 times with delays of 1s, 2s, 4s (via ``asyncio.sleep``). On exhausting the
retries, or on any other HTTP error / timeout / malformed XML, it degrades
gracefully to ``[]``.

No domain imports, no module-global mutable state. ``map_arxiv`` is a pure
helper so tests/fixtures map without an HTTP round-trip.
"""

from __future__ import annotations

import asyncio
import logging
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://export.arxiv.org/api/query"
TIMEOUT_SECONDS = 15.0

# Exponential backoff for arXiv's aggressive rate limiting.
MAX_RETRIES = 3
BACKOFF_DELAYS = (1.0, 2.0, 4.0)  # seconds; index by (attempt - 1)
RETRY_STATUSES = frozenset({429, 503})

_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"


def _text(elem: ET.Element | None) -> str:
    """Stripped text of an element, or "" when absent. Pure."""
    if elem is None or elem.text is None:
        return ""
    return elem.text.strip()


def map_arxiv(entry: ET.Element) -> dict:
    """Map one arXiv Atom ``<entry>`` element -> the neutral paper-like dict.

    Pure (no I/O). Operates on a parsed ``xml.etree`` element.
    """
    raw_entry_id = _text(entry.find(f"{_ATOM}id"))
    # entry_id looks like http://arxiv.org/abs/2401.01234v2 -> 2401.01234
    source_id = raw_entry_id.split("/")[-1].split("v")[0] if raw_entry_id else ""

    title = _text(entry.find(f"{_ATOM}title")).replace("\n", " ")
    title = " ".join(title.split())

    summary = _text(entry.find(f"{_ATOM}summary")).replace("\n", " ")
    summary = " ".join(summary.split())

    authors: list[str] = []
    for author in entry.findall(f"{_ATOM}author"):
        name = _text(author.find(f"{_ATOM}name"))
        if name:
            authors.append(name)

    # Year from <published> (e.g. "2024-01-15T...").
    year: int | None = None
    published = _text(entry.find(f"{_ATOM}published"))
    if len(published) >= 4 and published[:4].isdigit():
        year = int(published[:4])

    # Categories -> venue.
    categories = [
        c.get("term", "")
        for c in entry.findall(f"{_ATOM}category")
        if c.get("term")
    ]
    venue = ", ".join(categories)

    # DOI lives in the arxiv-namespaced <doi> element when present.
    doi = _text(entry.find(f"{_ARXIV}doi"))

    # PDF link: <link title="pdf" .../> or rel/type fallbacks.
    pdf_urls: list[str] = []
    html_url = raw_entry_id
    for link in entry.findall(f"{_ATOM}link"):
        href = link.get("href") or ""
        if not href:
            continue
        if link.get("title") == "pdf" or link.get("type") == "application/pdf":
            if href not in pdf_urls:
                pdf_urls.append(href)
        elif link.get("rel") == "alternate":
            html_url = href

    return {
        "source": "arxiv",
        "source_id": source_id,
        "title": title,
        "authors": authors,
        "abstract": summary,
        "year": year,
        "venue": venue,
        "citations": 0,  # arXiv exposes no citation count
        "doi": doi,
        "pdf_urls": pdf_urls,
        "url": html_url,
    }


async def search_arxiv(
    query: str,
    max_results: int = 10,
    **_kw,
) -> list[dict]:
    """Search arXiv; return neutral paper-like dicts.

    Retries with exponential backoff (1s, 2s, 4s) on 429/503 or transient
    request errors, up to ``MAX_RETRIES`` times. Returns ``[]`` on exhausted
    retries or any other HTTP error / timeout / malformed XML. 15s timeout.
    """
    params: dict[str, object] = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": min(max(max_results, 1), 100),
    }

    body: str | None = None
    attempt = 0
    while True:
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT_SECONDS, follow_redirects=True
            ) as client:
                response = await client.get(BASE_URL, params=params)
                if response.status_code in RETRY_STATUSES:
                    if attempt < MAX_RETRIES:
                        delay = BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS) - 1)]
                        logger.warning(
                            "arXiv %s for %r; backing off %.0fs (attempt %d/%d)",
                            response.status_code, query, delay, attempt + 1, MAX_RETRIES,
                        )
                        await asyncio.sleep(delay)
                        attempt += 1
                        continue
                    logger.warning("arXiv retries exhausted for %r", query)
                    return []
                response.raise_for_status()
                body = response.text
                break
        except httpx.TransportError as exc:
            # Connection/timeout errors are transient -> back off and retry.
            if attempt < MAX_RETRIES:
                delay = BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS) - 1)]
                logger.warning(
                    "arXiv transient error for %r: %s; backing off %.0fs "
                    "(attempt %d/%d)",
                    query, exc, delay, attempt + 1, MAX_RETRIES,
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue
            logger.warning("arXiv retries exhausted (transport) for %r", query)
            return []
        except httpx.HTTPError as exc:
            logger.warning("arXiv search failed for %r: %s", query, exc)
            return []

    if body is None:
        return []

    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        logger.warning("arXiv XML parse failed for %r: %s", query, exc)
        return []

    papers: list[dict] = []
    for entry in root.findall(f"{_ATOM}entry"):
        papers.append(map_arxiv(entry))
        if len(papers) >= max_results:
            break
    return papers
