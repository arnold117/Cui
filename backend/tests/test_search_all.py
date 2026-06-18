"""Tests for the multi-source orchestrator ``search_all``.

All adapters are monkeypatched to return canned neutral dicts (or raise), so
there is no real network. We assert aggregation, dedupe, registry selection,
and that one adapter raising still yields the others' results.
"""

from __future__ import annotations

import pytest

from anneal.search import multi
from anneal.search.multi import search_all


def _paper(source, source_id, doi="", **kw) -> dict:
    base = {
        "source": source,
        "source_id": source_id,
        "title": "A title",
        "authors": [],
        "abstract": "",
        "year": 2020,
        "venue": "",
        "citations": 0,
        "doi": doi,
        "pdf_urls": [],
        "url": "",
    }
    base.update(kw)
    return base


def _adapter(papers):
    async def fn(query, max_results=10, mailto=None, **kw):
        return papers
    return fn


def _raiser():
    async def fn(query, max_results=10, mailto=None, **kw):
        raise RuntimeError("source down")
    return fn


def _patch_registry(monkeypatch, mapping):
    monkeypatch.setattr(multi, "REGISTRY", mapping)


class TestSearchAll:
    async def test_aggregates_across_sources(self, monkeypatch):
        _patch_registry(monkeypatch, {
            "openalex": _adapter([_paper("openalex", "W1")]),
            "crossref": _adapter([_paper("crossref", "C1")]),
        })
        out = await search_all("q", sources=["openalex", "crossref"])
        ids = {(p["source"], p["source_id"]) for p in out}
        assert ids == {("openalex", "W1"), ("crossref", "C1")}

    async def test_dedupes_across_sources(self, monkeypatch):
        _patch_registry(monkeypatch, {
            "openalex": _adapter([_paper("openalex", "W1", doi="10.1/x")]),
            "crossref": _adapter([_paper("crossref", "C1", doi="10.1/x")]),
        })
        out = await search_all("q", sources=["openalex", "crossref"])
        assert len(out) == 1
        assert out[0]["sources"] == ["openalex", "crossref"]

    async def test_one_adapter_raising_yields_others(self, monkeypatch):
        _patch_registry(monkeypatch, {
            "openalex": _adapter([_paper("openalex", "W1")]),
            "crossref": _raiser(),
        })
        out = await search_all("q", sources=["openalex", "crossref"])
        assert len(out) == 1
        assert out[0]["source"] == "openalex"

    async def test_default_sources_used_when_none(self, monkeypatch):
        called = []

        def track(name):
            async def fn(query, max_results=10, mailto=None, **kw):
                called.append(name)
                return []
            return fn

        _patch_registry(monkeypatch, {n: track(n) for n in multi.DEFAULT_SOURCES})
        await search_all("q")
        assert sorted(called) == sorted(multi.DEFAULT_SOURCES)

    async def test_unknown_source_ignored(self, monkeypatch):
        _patch_registry(monkeypatch, {
            "openalex": _adapter([_paper("openalex", "W1")]),
        })
        out = await search_all("q", sources=["openalex", "nonsense"])
        assert len(out) == 1

    async def test_no_valid_sources_returns_empty(self, monkeypatch):
        _patch_registry(monkeypatch, {})
        assert await search_all("q", sources=["nonsense"]) == []

    async def test_mailto_and_max_forwarded(self, monkeypatch):
        captured = {}

        async def fn(query, max_results=10, mailto=None, **kw):
            captured["max_results"] = max_results
            captured["mailto"] = mailto
            return []

        _patch_registry(monkeypatch, {"openalex": fn})
        await search_all("q", sources=["openalex"], max_per_source=25,
                         mailto="me@example.com")
        assert captured["max_results"] == 25
        assert captured["mailto"] == "me@example.com"
