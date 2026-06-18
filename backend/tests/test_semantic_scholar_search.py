"""Tests for the Semantic Scholar adapter — pure mapping, graceful degradation,
the exponential-backoff retry path, and optional ``x-api-key`` support.

No real network: we monkeypatch ``httpx.AsyncClient`` with a fake client and
patch ``asyncio.sleep`` so backoff tests run instantly.
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
    def __init__(self, status_code: int = 200, json_data: dict | None = None) -> None:
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else SAMPLE_RESPONSE

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            req = httpx.Request("GET", semantic_scholar.BASE_URL)
            resp = httpx.Response(self.status_code, request=req)
            raise httpx.HTTPStatusError(
                str(self.status_code), request=req, response=resp
            )

    def json(self) -> dict:
        return self._json_data


def _client_returning(*responses):
    """Build a fake AsyncClient class that yields the given responses in order.

    Each element is either a _FakeResponse or an Exception to raise. The fake
    records the headers it was called with (last call) for assertions.
    """
    seq = list(responses)
    state = {"n": 0, "last_headers": None, "last_params": None}

    class _Client:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> None:
            return None

        async def get(self, url, params=None, headers=None):
            state["last_headers"] = headers
            state["last_params"] = params
            item = seq[state["n"]]
            state["n"] += 1
            if isinstance(item, Exception):
                raise item
            return item

    _Client.state = state
    return _Client


class _FakeAsyncClient:
    last_url: str | None = None
    last_params: dict | None = None
    last_headers: dict | None = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def get(self, url: str, params: dict | None = None, headers: dict | None = None):
        type(self).last_url = url
        type(self).last_params = params
        type(self).last_headers = headers
        return _FakeResponse(200, SAMPLE_RESPONSE)


class _RaisingAsyncClient(_FakeAsyncClient):
    async def get(self, url: str, params: dict | None = None, headers: dict | None = None):
        raise httpx.ConnectError("simulated failure")


@pytest.fixture
def no_sleep(monkeypatch):
    """Patch asyncio.sleep so backoff is instant; record the delays used."""
    delays: list[float] = []

    async def fake_sleep(d):
        delays.append(d)

    monkeypatch.setattr(semantic_scholar.asyncio, "sleep", fake_sleep)
    return delays


@pytest.fixture(autouse=True)
def _no_s2_key(monkeypatch):
    """Default: no API key in the environment (and don't read a real .env)."""
    monkeypatch.delenv("S2_API_KEY", raising=False)
    monkeypatch.setattr(semantic_scholar, "load_dotenv", lambda *a, **k: None)


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


class TestBackoff:
    async def test_backoff_retries_then_succeeds(self, monkeypatch, no_sleep):
        # Two 429s then a 200 -> results returned after retrying.
        client = _client_returning(
            _FakeResponse(429),
            _FakeResponse(429),
            _FakeResponse(200, SAMPLE_RESPONSE),
        )
        monkeypatch.setattr(semantic_scholar.httpx, "AsyncClient", client)

        results = await search_semantic_scholar("annealing")

        assert len(results) == 1  # succeeded after retrying
        assert results[0]["source_id"] == "abc123"
        assert client.state["n"] == 3  # two 429s + one success
        assert no_sleep == [1.0, 2.0]  # exponential delays for the 2 retries

    async def test_backoff_retries_on_503(self, monkeypatch, no_sleep):
        client = _client_returning(
            _FakeResponse(503),
            _FakeResponse(200, SAMPLE_RESPONSE),
        )
        monkeypatch.setattr(semantic_scholar.httpx, "AsyncClient", client)

        results = await search_semantic_scholar("q")

        assert len(results) == 1
        assert no_sleep == [1.0]

    async def test_backoff_exhausted_returns_empty(self, monkeypatch, no_sleep):
        client = _client_returning(
            _FakeResponse(429),
            _FakeResponse(429),
            _FakeResponse(429),
            _FakeResponse(429),
        )
        monkeypatch.setattr(semantic_scholar.httpx, "AsyncClient", client)

        results = await search_semantic_scholar("q")

        assert results == []
        assert no_sleep == [1.0, 2.0, 4.0]  # 3 retries before giving up

    async def test_transient_error_retries(self, monkeypatch, no_sleep):
        client = _client_returning(
            httpx.ConnectError("boom"),
            _FakeResponse(200, SAMPLE_RESPONSE),
        )
        monkeypatch.setattr(semantic_scholar.httpx, "AsyncClient", client)

        results = await search_semantic_scholar("q")

        assert len(results) == 1
        assert no_sleep == [1.0]

    async def test_non_retryable_http_error_returns_empty(self, monkeypatch, no_sleep):
        client = _client_returning(_FakeResponse(500))
        monkeypatch.setattr(semantic_scholar.httpx, "AsyncClient", client)

        results = await search_semantic_scholar("q")

        assert results == []
        assert no_sleep == []  # 500 is not retried


class TestApiKey:
    async def test_sends_x_api_key_header_when_set(self, monkeypatch, no_sleep):
        monkeypatch.setenv("S2_API_KEY", "secret-key")
        client = _client_returning(_FakeResponse(200, SAMPLE_RESPONSE))
        monkeypatch.setattr(semantic_scholar.httpx, "AsyncClient", client)

        results = await search_semantic_scholar("q")

        assert len(results) == 1
        assert client.state["last_headers"] == {"x-api-key": "secret-key"}

    async def test_no_api_key_header_when_unset(self, monkeypatch, no_sleep):
        # _no_s2_key autouse fixture already deleted S2_API_KEY.
        client = _client_returning(_FakeResponse(200, SAMPLE_RESPONSE))
        monkeypatch.setattr(semantic_scholar.httpx, "AsyncClient", client)

        results = await search_semantic_scholar("q")

        assert len(results) == 1
        # Keyless: no x-api-key header passed.
        assert client.state["last_headers"] == {}
        assert "x-api-key" not in (client.state["last_headers"] or {})
