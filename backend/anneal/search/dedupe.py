"""Deduplicate neutral paper-like dicts across sources.

Pure, deterministic, no I/O. Cherry-picks LitScribe's ``dedup_papers``
semantics but operates on the neutral dict schema produced by the search
adapters.

Merge-key priority for identifying duplicates:
  1. normalized DOI (lowercased, stripped) when present;
  2. else ``"source:source_id"``;
  3. else a normalized ``"title|year"`` fallback (lowercased, whitespace-
     collapsed title).

When duplicates merge we keep the first-seen primary ``source``/``source_id``
and overall first-appearance order, but enrich the kept record:
  - keep the richer (longer) abstract;
  - union ``pdf_urls`` (dedupe, preserve order);
  - keep the max ``citations``;
  - record every contributing source in a new ``"sources"`` list (union, in
    order of first appearance).
"""

from __future__ import annotations


def _norm_doi(doi: str) -> str:
    return (doi or "").strip().lower()


def _norm_title(title: str) -> str:
    return " ".join((title or "").split()).lower()


def _merge_key(paper: dict) -> str:
    """Compute the dedupe key for one neutral paper dict. Pure."""
    doi = _norm_doi(paper.get("doi") or "")
    if doi:
        return f"doi:{doi}"

    source = paper.get("source") or ""
    source_id = paper.get("source_id") or ""
    if source_id:
        return f"sid:{source}:{source_id}"

    title = _norm_title(paper.get("title") or "")
    year = paper.get("year")
    return f"ty:{title}|{year}"


def _union_urls(existing: list[str], incoming: list[str]) -> list[str]:
    merged = list(existing)
    for url in incoming:
        if url and url not in merged:
            merged.append(url)
    return merged


def dedupe(papers: list[dict]) -> list[dict]:
    """Collapse duplicate papers into enriched records. Pure, deterministic.

    Returns a new list, preserving overall first-appearance order. Each kept
    record gains a ``"sources"`` key listing every source it appeared in.
    """
    by_key: dict[str, dict] = {}
    order: list[str] = []

    for paper in papers:
        key = _merge_key(paper)
        source = paper.get("source") or ""

        if key not in by_key:
            merged = dict(paper)
            merged["sources"] = [source] if source else []
            by_key[key] = merged
            order.append(key)
            continue

        existing = by_key[key]

        # Richer (longer) abstract wins.
        new_abstract = paper.get("abstract") or ""
        if len(new_abstract) > len(existing.get("abstract") or ""):
            existing["abstract"] = new_abstract

        existing["pdf_urls"] = _union_urls(
            existing.get("pdf_urls") or [], paper.get("pdf_urls") or []
        )

        existing["citations"] = max(
            existing.get("citations") or 0, paper.get("citations") or 0
        )

        if source and source not in existing["sources"]:
            existing["sources"].append(source)

    return [by_key[key] for key in order]
