"""External live literature sources for the dialogue surface (slice1, 2026-09).

Thin host-side aggregation over the archived arXiv/OpenAlex fetchers
(``cui.legacy_archive.search``), normalised into dialogue items:

    {locator, title, excerpt, url, source}

Locators keep the corpus prefixes where possible (arxiv:<id> / doi:<doi>) and
fall back to ``openalex:<id>``; excerpts are capped so downstream LLM prompts
never blow up. Both fetchers degrade gracefully ([] on any error), so the
dialogue survives a dead network — the corpus always still works.
"""
from __future__ import annotations

import asyncio
import re

from cui.legacy_archive.search.arxiv import search_arxiv
from cui.legacy_archive.search.openalex import search_openalex

EXCERPT_CAP = 1500


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
    if doi:
        locator = f"doi:{doi.lower()}"
    if not locator:
        match = re.search(r"/works/(W\d+)$", url)
        if match:
            locator = f"openalex:{match.group(1)}"
    if not locator:
        return None
    return {"locator": locator, "title": title, "excerpt": _excerpt(abstract), "url": url, "source": source or "external"}


async def external_search(query: str, per_source: int = 5) -> list[dict]:
    """arXiv + OpenAlex in parallel; deduped by locator (first source wins)."""
    results = await asyncio.gather(
        search_arxiv(query, max_results=per_source),
        search_openalex(query, max_results=per_source),
    )
    seen: set[str] = set()
    items: list[dict] = []
    for raw in results:
        for item in raw:
            normalised = _normalise(item)
            if normalised is None or normalised["locator"] in seen:
                continue
            seen.add(normalised["locator"])
            items.append(normalised)
    return items
