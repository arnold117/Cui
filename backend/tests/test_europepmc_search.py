"""Tests for the EuropePMC search adapter — pure mapping + graceful degradation.

No real network: we monkeypatch ``httpx.AsyncClient`` with a fake client.
"""

from __future__ import annotations

import httpx
import pytest

from anneal.search import europe_pmc
from anneal.search.europe_pmc import map_europepmc, search_europepmc


SAMPLE_HIT = {
    "id": "33000000",
    "source": "MED",
    "pmid": "33000000",
    "pmcid": "PMC7000000",
    "isOpenAccess": "Y",
    "title": "Annealing methods for adversarial writing engines",
    "authorString": "Lovelace A; Turing A; Babbage C.",
    "abstractText": "The grilled idea survives.",
    "pubYear": "2020",
    "citedByCount": 42,
    "doi": "10.1234/abc.2020.42",
    "journalInfo": {"journal": {"title": "Journal of Forged Drafts"}},
}

SAMPLE_RESPONSE = {"resultList": {"result": [SAMPLE_HIT]}}


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
        raise httpx.ReadTimeout("simulated timeout")


class TestMapEuropePMC:
    def test_maps_neutral_schema(self):
        d = map_europepmc(SAMPLE_HIT)

        assert d["source"] == "europepmc"
        assert d["source_id"] == "33000000"  # pmid preferred
        assert d["title"] == "Annealing methods for adversarial writing engines"
        assert d["authors"] == ["Lovelace A", "Turing A", "Babbage C"]
        assert d["abstract"] == "The grilled idea survives."
        assert d["year"] == 2020
        assert d["venue"] == "Journal of Forged Drafts"
        assert d["citations"] == 42
        assert d["doi"] == "10.1234/abc.2020.42"
        assert d["pdf_urls"] == ["https://europepmc.org/articles/PMC7000000/pdf"]
        assert d["url"] == "https://europepmc.org/article/MED/33000000"

    def test_exact_schema_keys(self):
        d = map_europepmc(SAMPLE_HIT)
        assert set(d.keys()) == {
            "source", "source_id", "title", "authors", "abstract", "year",
            "venue", "citations", "doi", "pdf_urls", "url",
        }

    def test_missing_fields_default_gracefully(self):
        d = map_europepmc({"id": "X1"})
        assert d["source_id"] == "X1"
        assert d["title"] == ""
        assert d["authors"] == []
        assert d["abstract"] == ""
        assert d["year"] is None
        assert d["venue"] == ""
        assert d["citations"] == 0
        assert d["doi"] == ""
        assert d["pdf_urls"] == []

    def test_no_pdf_when_not_open_access(self):
        d = map_europepmc({"id": "X1", "pmcid": "PMC1", "isOpenAccess": "N"})
        assert d["pdf_urls"] == []


class TestSearchEuropePMC:
    async def test_maps_results(self, monkeypatch):
        monkeypatch.setattr(europe_pmc.httpx, "AsyncClient", _FakeAsyncClient)
        results = await search_europepmc("annealing", max_results=5)
        assert len(results) == 1
        assert results[0]["source_id"] == "33000000"

    async def test_sends_json_format_and_pagesize(self, monkeypatch):
        monkeypatch.setattr(europe_pmc.httpx, "AsyncClient", _FakeAsyncClient)
        await search_europepmc("q", max_results=7)
        assert _FakeAsyncClient.last_params["format"] == "json"
        assert _FakeAsyncClient.last_params["query"] == "q"
        assert _FakeAsyncClient.last_params["pageSize"] == 7

    async def test_http_error_returns_empty(self, monkeypatch):
        monkeypatch.setattr(europe_pmc.httpx, "AsyncClient", _RaisingAsyncClient)
        assert await search_europepmc("q") == []
