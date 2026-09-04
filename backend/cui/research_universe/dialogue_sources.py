"""External live literature sources for the dialogue surface (slice1, 2026-09).

Thin host-side aggregation over the archived arXiv/OpenAlex fetchers
(``cui.legacy_archive.search``), normalised into dialogue items:

    {locator, title, excerpt, url, source}

Locators keep the corpus prefixes where possible (arxiv:<id> / doi:<doi>) and
fall back to ``openalex:<id>``; excerpts are capped so downstream LLM prompts
never blow up. Both fetchers degrade gracefully ([] on any error), so the
dialogue survives a dead network — the corpus always still works.

Rate-limit policy (arXiv 429s aggressively and the archive fetcher already
backs off 1s/2s/4s): the arXiv leg gets a hard wall-clock cap so a throttled
arXiv cannot stall the whole search, and OpenAlex is asked for more results to
compensate when arXiv is unavailable. ``doi:10.48550/arxiv.*`` records are
canonicalised to ``arxiv:<id>`` so they dedupe against the corpus.
"""
from __future__ import annotations

import asyncio
import re

from cui.legacy_archive.search.arxiv import search_arxiv
from cui.legacy_archive.search.openalex import search_openalex

EXCERPT_CAP = 1500

# Hard cap on the arXiv leg: 1s+2s+4s backoff already means a 429 stalls the
# whole dialogue search for ~7s; past this we take OpenAlex's results only.
ARXIV_WALL_SECONDS = 5.0
ARXIV_MAX_PER_SOURCE = 5


def _excerpt(abstract: str | None) -> str:
    return " ".join((abstract or "").split())[:EXCERPT_CAP]


def _normalise(item: dict) -> dict | None:
    title = (item.get("title") or "").strip()
    abstract = (item.get("abstract") or "").strip()
    source = item.get("source") or ""
    if not title or not abstract:
        return None
    url = item.get("url") or item.get("pdf_url") or ""
    locator = ""
    arxiv_id = (item.get("arxiv_id") or item.get("id") or "")
    if source == "arxiv" or re.match(r"^\d{4}\.\d{4,5}", arxiv_id):
        arxiv_id = re.sub(r"v\d+$", "", arxiv_id)
        locator = f"arxiv:{arxiv_id}"
    doi = (item.get("doi") or "").strip()
    # OpenAlex cites arXiv preprints as doi:10.48550/arxiv.XXXX — treat them as
    # the arXiv record (dedupes against the corpus, links resolve to arXiv).
    m = re.match(r"^10\.48550/arxiv\.(\d{4}\.\d{4,5})(?:v\d+)?$", doi.lower())
    if m:
        locator = f"arxiv:{m.group(1)}"
    elif doi:
        locator = f"doi:{doi.lower()}"
    if not locator:
        match = re.search(r"/works/(W\d+)$", url)
        if match:
            locator = f"openalex:{match.group(1)}"
    if not locator:
        return None
    return {"locator": locator, "title": title, "excerpt": _excerpt(abstract), "url": url, "source": source or "external"}


async def external_search(query: str, per_source: int = 6) -> list[dict]:
    """arXiv + OpenAlex in parallel; deduped by locator (first source wins).

    arXiv is capped at ``ARXIV_MAX_PER_SOURCE`` and at ``ARXIV_WALL_SECONDS``;
    OpenAlex gets ``per_source + 3`` so a throttled arXiv still leaves a usable
    external pool. Errors degrade to fewer items, never to a raised error.
    """
    arxiv_max = min(ARXIV_MAX_PER_SOURCE, per_source)
    openalex_max = per_source + 3
    arxiv_task = asyncio.ensure_future(search_arxiv(query, max_results=arxiv_max))
    openalex_task = asyncio.ensure_future(search_openalex(query, max_results=openalex_max))
    try:
        arxiv_raw = await asyncio.wait_for(arxiv_task, timeout=ARXIV_WALL_SECONDS)
    except Exception:
        arxiv_raw = []
        if not arxiv_task.done():
            arxiv_task.cancel()
    openalex_raw = await asyncio.gather(openalex_task, return_exceptions=True)
    openalex_raw = openalex_raw[0] if openalex_raw and not isinstance(openalex_raw[0], BaseException) else []

    seen: set[str] = set()
    items: list[dict] = []
    for raw in (arxiv_raw, openalex_raw):
        for item in raw:
            normalised = _normalise(item)
            if normalised is None or normalised["locator"] in seen:
                continue
            seen.add(normalised["locator"])
            items.append(normalised)
    return items
