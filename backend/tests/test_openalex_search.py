"""Tests for the OpenAlex search adapter — pure mapping + graceful degradation.

No real network: we monkeypatch ``httpx.AsyncClient`` with a fake client whose
``get`` returns a canned response (or raises) so we exercise the mapping and the
error-handling path deterministically.
"""

from __future__ import annotations

import httpx
import pytest

from anneal.search import openalex
from anneal.search.openalex import (
    map_work,
    reconstruct_abstract,
    search_openalex,
)


# ---------------------------------------------------------------------------
# Realistic OpenAlex work fixture (with inverted-index abstract)
# ---------------------------------------------------------------------------

SAMPLE_WORK = {
    "id": "https://openalex.org/W2042820948",
    "doi": "https://doi.org/10.1234/abc.2020.42",
    "display_name": "Annealing methods for adversarial writing engines",
    "publication_year": 2020,
    "cited_by_count": 137,
    "authorships": [
        {"author": {"display_name": "Ada Lovelace"}},
        {"author": {"display_name": "Alan Turing"}},
        {"author": {}},  # missing display_name -> dropped
    ],
    "primary_location": {
        "source": {"display_name": "Journal of Forged Drafts"},
    },
    "locations": [
        {"pdf_url": "https://example.org/paper.pdf"},
        {"pdf_url": None},
        {"pdf_url": "https://example.org/paper.pdf"},  # duplicate -> deduped
        {"pdf_url": "https://mirror.example.org/paper.pdf"},
    ],
    # "The grilled idea survives" as an inverted index.
    "abstract_inverted_index": {
        "The": [0],
        "grilled": [1],
        "idea": [2],
        "survives": [3],
    },
}

SAMPLE_RESPONSE = {"results": [SAMPLE_WORK]}


# ---------------------------------------------------------------------------
# Fake httpx client
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, json_data: dict) -> None:
        self._json_data = json_data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._json_data


class _FakeAsyncClient:
    """Stand-in for httpx.AsyncClient. Records the last request for assertions."""

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
        raise httpx.ConnectTimeout("simulated timeout")


# ---------------------------------------------------------------------------
# reconstruct_abstract (pure helper)
# ---------------------------------------------------------------------------


class TestReconstructAbstract:
    def test_rebuilds_in_order(self):
        inv = {"hello": [1], "world": [2], "say": [0]}
        assert reconstruct_abstract(inv) == "say hello world"

    def test_repeated_word_positions(self):
        inv = {"the": [0, 2], "cat": [1], "hat": [3]}
        assert reconstruct_abstract(inv) == "the cat the hat"

    def test_empty_returns_empty_string(self):
        assert reconstruct_abstract({}) == ""

    def test_none_returns_empty_string(self):
        assert reconstruct_abstract(None) == ""


# ---------------------------------------------------------------------------
# map_work (pure mapping)
# ---------------------------------------------------------------------------


class TestMapWork:
    def test_maps_neutral_schema(self):
        d = map_work(SAMPLE_WORK)

        assert d["source"] == "openalex"
        assert d["source_id"] == "W2042820948"  # url prefix stripped
        assert d["title"] == "Annealing methods for adversarial writing engines"
        assert d["authors"] == ["Ada Lovelace", "Alan Turing"]  # empty dropped
        assert d["abstract"] == "The grilled idea survives"
        assert d["year"] == 2020
        assert d["venue"] == "Journal of Forged Drafts"
        assert d["citations"] == 137
        assert d["doi"] == "10.1234/abc.2020.42"  # url prefix stripped
        assert d["pdf_urls"] == [
            "https://example.org/paper.pdf",
            "https://mirror.example.org/paper.pdf",
        ]
        assert d["url"] == "https://openalex.org/W2042820948"

    def test_exact_schema_keys(self):
        d = map_work(SAMPLE_WORK)
        assert set(d.keys()) == {
            "source",
            "source_id",
            "title",
            "authors",
            "abstract",
            "year",
            "venue",
            "citations",
            "doi",
            "pdf_urls",
            "url",
        }

    def test_missing_fields_default_gracefully(self):
        d = map_work({"id": "https://openalex.org/W1"})
        assert d["source_id"] == "W1"
        assert d["title"] == ""
        assert d["authors"] == []
        assert d["abstract"] == ""
        assert d["year"] is None
        assert d["venue"] == ""
        assert d["citations"] == 0
        assert d["doi"] == ""
        assert d["pdf_urls"] == []

    def test_non_int_year_becomes_none(self):
        d = map_work({"id": "x", "publication_year": None})
        assert d["year"] is None


# ---------------------------------------------------------------------------
# search_openalex (async, network mocked)
# ---------------------------------------------------------------------------


class TestSearchOpenAlex:
    async def test_maps_results(self, monkeypatch):
        monkeypatch.setattr(openalex.httpx, "AsyncClient", _FakeAsyncClient)

        results = await search_openalex("annealing", max_results=5)

        assert len(results) == 1
        assert results[0]["source_id"] == "W2042820948"
        assert results[0]["abstract"] == "The grilled idea survives"

    async def test_passes_mailto_when_given(self, monkeypatch):
        monkeypatch.setattr(openalex.httpx, "AsyncClient", _FakeAsyncClient)

        await search_openalex("q", max_results=3, mailto="me@example.com")

        assert _FakeAsyncClient.last_params["mailto"] == "me@example.com"
        assert _FakeAsyncClient.last_params["search"] == "q"
        assert _FakeAsyncClient.last_params["per_page"] == 3

    async def test_omits_mailto_when_none(self, monkeypatch):
        _FakeAsyncClient.last_params = None
        monkeypatch.setattr(openalex.httpx, "AsyncClient", _FakeAsyncClient)

        await search_openalex("q")

        assert "mailto" not in _FakeAsyncClient.last_params

    async def test_respects_max_results(self, monkeypatch):
        many = {"results": [dict(SAMPLE_WORK, id=f"https://openalex.org/W{i}")
                            for i in range(20)]}

        class _ManyClient(_FakeAsyncClient):
            async def get(self, url, params=None):
                return _FakeResponse(many)

        monkeypatch.setattr(openalex.httpx, "AsyncClient", _ManyClient)
        results = await search_openalex("q", max_results=5)
        assert len(results) == 5

    async def test_http_error_returns_empty(self, monkeypatch):
        monkeypatch.setattr(openalex.httpx, "AsyncClient", _RaisingAsyncClient)
        results = await search_openalex("q")
        assert results == []

    async def test_status_error_returns_empty(self, monkeypatch):
        class _StatusErrClient(_FakeAsyncClient):
            async def get(self, url, params=None):
                req = httpx.Request("GET", url)
                resp = httpx.Response(500, request=req)
                return _RaisingStatus(resp)

        class _RaisingStatus:
            def __init__(self, resp):
                self._resp = resp

            def raise_for_status(self):
                raise httpx.HTTPStatusError(
                    "500", request=self._resp.request, response=self._resp
                )

            def json(self):
                return {}

        monkeypatch.setattr(openalex.httpx, "AsyncClient", _StatusErrClient)
        results = await search_openalex("q")
        assert results == []
