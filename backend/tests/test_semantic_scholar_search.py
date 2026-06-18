"""Tests for the Semantic Scholar adapter — pure mapping + graceful degradation.

No real network: we monkeypatch ``httpx.AsyncClient`` with a fake client.
"""

from __future__ import annotations

import httpx
import pytest

from anneal.search import semantic_scholar
from anneal.search.semantic_scholar import (
    map_semantic_scholar,
    search_semantic_scholar,
)


SAMPLE_PAPER = {
    "paperId": "abc123",
    "title": "Annealing methods for adversarial writing engines",
    "abstract": "The grilled idea survives.",
    "year": 2020,
    "venue": "Journal of Forged Drafts",
    "citationCount": 137,
    "externalIds": {"DOI": "10.1234/abc.2020.42", "ArXiv": "2001.00001"},
    "authors": [
        {"name": "Ada Lovelace"},
        {"name": "Alan Turing"},
        {"name": ""},  # dropped
    ],
    "openAccessPdf": {"url": "https://example.org/s2.pdf"},
    "url": "https://www.semanticscholar.org/paper/abc123",
}

SAMPLE_RESPONSE = {"data": [SAMPLE_PAPER]}


class _FakeResponse:
    def __init__(self, json_data: dict) -> None:
        self._json_data = json_data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._json_data


class _FakeAsyncClient:
    last_url: str | None = None
    last_params: dict | None = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def get(self, url: str, params: dict | None = None):
        type(self).last_url = url
        type(self).last_params = params
        return _FakeResponse(SAMPLE_RESPONSE)


class _RaisingAsyncClient(_FakeAsyncClient):
    async def get(self, url: str, params: dict | None = None):
        raise httpx.ConnectError("simulated failure")


class TestMapSemanticScholar:
    def test_maps_neutral_schema(self):
        d = map_semantic_scholar(SAMPLE_PAPER)

        assert d["source"] == "semantic_scholar"
        assert d["source_id"] == "abc123"
        assert d["title"] == "Annealing methods for adversarial writing engines"
        assert d["authors"] == ["Ada Lovelace", "Alan Turing"]
        assert d["abstract"] == "The grilled idea survives."
        assert d["year"] == 2020
        assert d["venue"] == "Journal of Forged Drafts"
        assert d["citations"] == 137
        assert d["doi"] == "10.1234/abc.2020.42"  # externalIds.DOI
        assert d["pdf_urls"] == ["https://example.org/s2.pdf"]
        assert d["url"] == "https://www.semanticscholar.org/paper/abc123"

    def test_exact_schema_keys(self):
        d = map_semantic_scholar(SAMPLE_PAPER)
        assert set(d.keys()) == {
            "source", "source_id", "title", "authors", "abstract", "year",
            "venue", "citations", "doi", "pdf_urls", "url",
        }

    def test_missing_fields_default_gracefully(self):
        d = map_semantic_scholar({"paperId": "p1"})
        assert d["source_id"] == "p1"
        assert d["title"] == ""
        assert d["authors"] == []
        assert d["abstract"] == ""
        assert d["year"] is None
        assert d["venue"] == ""
        assert d["citations"] == 0
        assert d["doi"] == ""
        assert d["pdf_urls"] == []

    def test_no_doi_when_external_ids_lacks_one(self):
        d = map_semantic_scholar({"paperId": "p1", "externalIds": {"ArXiv": "x"}})
        assert d["doi"] == ""


class TestSearchSemanticScholar:
    async def test_maps_results(self, monkeypatch):
        monkeypatch.setattr(semantic_scholar.httpx, "AsyncClient", _FakeAsyncClient)
        results = await search_semantic_scholar("annealing", max_results=5)
        assert len(results) == 1
        assert results[0]["source_id"] == "abc123"

    async def test_sends_query_limit_fields(self, monkeypatch):
        monkeypatch.setattr(semantic_scholar.httpx, "AsyncClient", _FakeAsyncClient)
        await search_semantic_scholar("q", max_results=4)
        assert _FakeAsyncClient.last_params["query"] == "q"
        assert _FakeAsyncClient.last_params["limit"] == 4
        assert "externalIds" in _FakeAsyncClient.last_params["fields"]
        assert "openAccessPdf" in _FakeAsyncClient.last_params["fields"]

    async def test_http_error_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            semantic_scholar.httpx, "AsyncClient", _RaisingAsyncClient
        )
        assert await search_semantic_scholar("q") == []
