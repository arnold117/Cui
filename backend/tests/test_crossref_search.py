"""Tests for the CrossRef search adapter — pure mapping + graceful degradation.

No real network: we monkeypatch ``httpx.AsyncClient`` with a fake client whose
``get`` returns a canned response (or raises) so we exercise the mapping and the
error-handling path deterministically.
"""

from __future__ import annotations

import httpx
import pytest

from anneal.search import crossref
from anneal.search.crossref import map_crossref, search_crossref


SAMPLE_ITEM = {
    "DOI": "10.1234/abc.2020.42",
    "title": ["Annealing methods for adversarial writing engines"],
    "author": [
        {"given": "Ada", "family": "Lovelace"},
        {"given": "Alan", "family": "Turing"},
        {"family": "Anonymous"},  # no given name -> still kept
        {},  # empty -> dropped
    ],
    "abstract": "<jats:p>The grilled idea <jats:bold>survives</jats:bold>.</jats:p>",
    "published": {"date-parts": [[2020, 5, 1]]},
    "container-title": ["Journal of Forged Drafts"],
    "is-referenced-by-count": 137,
    "URL": "https://doi.org/10.1234/abc.2020.42",
}

SAMPLE_RESPONSE = {"message": {"items": [SAMPLE_ITEM]}}


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
        raise httpx.ConnectTimeout("simulated timeout")


class TestMapCrossref:
    def test_maps_neutral_schema(self):
        d = map_crossref(SAMPLE_ITEM)

        assert d["source"] == "crossref"
        assert d["source_id"] == "10.1234/abc.2020.42"
        assert d["title"] == "Annealing methods for adversarial writing engines"
        assert d["authors"] == ["Ada Lovelace", "Alan Turing", "Anonymous"]
        assert d["abstract"] == "The grilled idea survives."  # JATS tags stripped
        assert d["year"] == 2020
        assert d["venue"] == "Journal of Forged Drafts"
        assert d["citations"] == 137
        assert d["doi"] == "10.1234/abc.2020.42"
        assert d["pdf_urls"] == []
        assert d["url"] == "https://doi.org/10.1234/abc.2020.42"

    def test_exact_schema_keys(self):
        d = map_crossref(SAMPLE_ITEM)
        assert set(d.keys()) == {
            "source", "source_id", "title", "authors", "abstract", "year",
            "venue", "citations", "doi", "pdf_urls", "url",
        }

    def test_missing_fields_default_gracefully(self):
        d = map_crossref({"DOI": "10.9/x"})
        assert d["source_id"] == "10.9/x"
        assert d["title"] == ""
        assert d["authors"] == []
        assert d["abstract"] == ""
        assert d["year"] is None
        assert d["venue"] == ""
        assert d["citations"] == 0
        assert d["doi"] == "10.9/x"
        assert d["pdf_urls"] == []
        assert d["url"] == "https://doi.org/10.9/x"

    def test_falls_back_to_issued_year(self):
        d = map_crossref({"DOI": "x", "issued": {"date-parts": [[2018]]}})
        assert d["year"] == 2018


class TestSearchCrossref:
    async def test_maps_results(self, monkeypatch):
        monkeypatch.setattr(crossref.httpx, "AsyncClient", _FakeAsyncClient)
        results = await search_crossref("annealing", max_results=5)
        assert len(results) == 1
        assert results[0]["doi"] == "10.1234/abc.2020.42"
        assert results[0]["abstract"] == "The grilled idea survives."

    async def test_passes_mailto_and_params(self, monkeypatch):
        monkeypatch.setattr(crossref.httpx, "AsyncClient", _FakeAsyncClient)
        await search_crossref("q", max_results=3, mailto="me@example.com")
        assert _FakeAsyncClient.last_params["mailto"] == "me@example.com"
        assert _FakeAsyncClient.last_params["query"] == "q"
        assert _FakeAsyncClient.last_params["rows"] == 3

    async def test_omits_mailto_when_none(self, monkeypatch):
        _FakeAsyncClient.last_params = None
        monkeypatch.setattr(crossref.httpx, "AsyncClient", _FakeAsyncClient)
        await search_crossref("q")
        assert "mailto" not in _FakeAsyncClient.last_params

    async def test_http_error_returns_empty(self, monkeypatch):
        monkeypatch.setattr(crossref.httpx, "AsyncClient", _RaisingAsyncClient)
        assert await search_crossref("q") == []
