"""Tests for the arXiv search adapter — pure mapping, graceful degradation,
and the exponential-backoff retry path.

No real network: we monkeypatch ``httpx.AsyncClient`` with a fake client and
patch ``asyncio.sleep`` so backoff tests run instantly.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

import httpx
import pytest

from anneal.search import arxiv
from anneal.search.arxiv import map_arxiv, search_arxiv


# A realistic arXiv Atom feed: one entry with a DOI and a pdf link.
SAMPLE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2001.00001v2</id>
    <title>Annealing methods for
      adversarial writing engines</title>
    <summary>The grilled
      idea survives.</summary>
    <published>2020-01-03T00:00:00Z</published>
    <author><name>Ada Lovelace</name></author>
    <author><name>Alan Turing</name></author>
    <arxiv:doi>10.1234/abc.2020.42</arxiv:doi>
    <category term="cs.CL"/>
    <category term="cs.AI"/>
    <link rel="alternate" type="text/html" href="http://arxiv.org/abs/2001.00001v2"/>
    <link title="pdf" rel="related" type="application/pdf"
          href="http://arxiv.org/pdf/2001.00001v2"/>
  </entry>
</feed>
"""


class _FakeResponse:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            req = httpx.Request("GET", arxiv.BASE_URL)
            resp = httpx.Response(self.status_code, request=req)
            raise httpx.HTTPStatusError(
                str(self.status_code), request=req, response=resp
            )


def _client_returning(*responses):
    """Build a fake AsyncClient class that yields the given responses in order.

    Each element is either a _FakeResponse or an Exception to raise.
    """
    seq = list(responses)
    calls = {"n": 0}

    class _Client:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> None:
            return None

        async def get(self, url, params=None):
            item = seq[calls["n"]]
            calls["n"] += 1
            if isinstance(item, Exception):
                raise item
            return item

    _Client.calls = calls
    return _Client


@pytest.fixture
def no_sleep(monkeypatch):
    """Patch asyncio.sleep so backoff is instant; record the delays used."""
    delays: list[float] = []

    async def fake_sleep(d):
        delays.append(d)

    monkeypatch.setattr(arxiv.asyncio, "sleep", fake_sleep)
    return delays


class TestArxivConfig:
    def test_base_url_is_https(self):
        # arXiv 301-redirects http -> https; the base URL must be https so the
        # adapter does not depend on redirect-following in production.
        assert arxiv.BASE_URL == "https://export.arxiv.org/api/query"
        assert arxiv.BASE_URL.startswith("https://")

    async def test_client_constructed_with_follow_redirects(self, monkeypatch):
        # Belt-and-suspenders: the AsyncClient must be built with
        # follow_redirects=True so any future redirect is followed too.
        captured_kwargs = {}

        class _Client:
            def __init__(self, *a, **k):
                captured_kwargs.update(k)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return None

            async def get(self, url, params=None):
                return _FakeResponse(200, SAMPLE_FEED)

        monkeypatch.setattr(arxiv.httpx, "AsyncClient", _Client)
        await search_arxiv("annealing")
        assert captured_kwargs.get("follow_redirects") is True


class TestMapArxiv:
    def test_maps_neutral_schema(self):
        root = ET.fromstring(SAMPLE_FEED)
        entry = root.find("{http://www.w3.org/2005/Atom}entry")
        d = map_arxiv(entry)

        assert d["source"] == "arxiv"
        assert d["source_id"] == "2001.00001"  # version + abs/ stripped
        assert d["title"] == "Annealing methods for adversarial writing engines"
        assert d["authors"] == ["Ada Lovelace", "Alan Turing"]
        assert d["abstract"] == "The grilled idea survives."
        assert d["year"] == 2020
        assert d["venue"] == "cs.CL, cs.AI"
        assert d["citations"] == 0
        assert d["doi"] == "10.1234/abc.2020.42"
        assert d["pdf_urls"] == ["http://arxiv.org/pdf/2001.00001v2"]
        assert d["url"] == "http://arxiv.org/abs/2001.00001v2"

    def test_exact_schema_keys(self):
        root = ET.fromstring(SAMPLE_FEED)
        entry = root.find("{http://www.w3.org/2005/Atom}entry")
        d = map_arxiv(entry)
        assert set(d.keys()) == {
            "source", "source_id", "title", "authors", "abstract", "year",
            "venue", "citations", "doi", "pdf_urls", "url",
        }

    def test_missing_doi_defaults_empty(self):
        feed = """<feed xmlns="http://www.w3.org/2005/Atom">
          <entry><id>http://arxiv.org/abs/1234.5678v1</id>
          <title>t</title><summary>s</summary>
          <published>2019-01-01T00:00:00Z</published></entry></feed>"""
        entry = ET.fromstring(feed).find("{http://www.w3.org/2005/Atom}entry")
        d = map_arxiv(entry)
        assert d["doi"] == ""
        assert d["pdf_urls"] == []
        assert d["year"] == 2019


class TestSearchArxiv:
    async def test_maps_results(self, monkeypatch):
        monkeypatch.setattr(
            arxiv.httpx, "AsyncClient", _client_returning(_FakeResponse(200, SAMPLE_FEED))
        )
        results = await search_arxiv("annealing", max_results=5)
        assert len(results) == 1
        assert results[0]["source_id"] == "2001.00001"

    async def test_sends_search_query(self, monkeypatch):
        captured = {}

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return None

            async def get(self, url, params=None):
                captured.update(params)
                return _FakeResponse(200, SAMPLE_FEED)

        monkeypatch.setattr(arxiv.httpx, "AsyncClient", _Client)
        await search_arxiv("neural nets", max_results=3)
        assert captured["search_query"] == "all:neural nets"
        assert captured["max_results"] == 3

    async def test_backoff_retries_then_succeeds(self, monkeypatch, no_sleep):
        client = _client_returning(
            _FakeResponse(503, ""),
            _FakeResponse(503, ""),
            _FakeResponse(200, SAMPLE_FEED),
        )
        monkeypatch.setattr(arxiv.httpx, "AsyncClient", client)

        results = await search_arxiv("annealing")

        assert len(results) == 1  # succeeded after retrying
        assert client.calls["n"] == 3  # two failures + one success
        assert no_sleep == [1.0, 2.0]  # exponential delays for the 2 retries

    async def test_backoff_retries_on_429(self, monkeypatch, no_sleep):
        client = _client_returning(
            _FakeResponse(429, ""),
            _FakeResponse(200, SAMPLE_FEED),
        )
        monkeypatch.setattr(arxiv.httpx, "AsyncClient", client)

        results = await search_arxiv("q")

        assert len(results) == 1
        assert no_sleep == [1.0]

    async def test_backoff_exhausted_returns_empty(self, monkeypatch, no_sleep):
        client = _client_returning(
            _FakeResponse(503, ""),
            _FakeResponse(503, ""),
            _FakeResponse(503, ""),
            _FakeResponse(503, ""),
        )
        monkeypatch.setattr(arxiv.httpx, "AsyncClient", client)

        results = await search_arxiv("q")

        assert results == []
        assert no_sleep == [1.0, 2.0, 4.0]  # 3 retries before giving up

    async def test_transient_error_retries(self, monkeypatch, no_sleep):
        client = _client_returning(
            httpx.ConnectError("boom"),
            _FakeResponse(200, SAMPLE_FEED),
        )
        monkeypatch.setattr(arxiv.httpx, "AsyncClient", client)

        results = await search_arxiv("q")

        assert len(results) == 1
        assert no_sleep == [1.0]

    async def test_non_retryable_http_error_returns_empty(self, monkeypatch, no_sleep):
        client = _client_returning(_FakeResponse(500, ""))
        monkeypatch.setattr(arxiv.httpx, "AsyncClient", client)

        results = await search_arxiv("q")

        assert results == []
        assert no_sleep == []  # 500 is not retried

    async def test_malformed_xml_returns_empty(self, monkeypatch):
        client = _client_returning(_FakeResponse(200, "<not valid xml"))
        monkeypatch.setattr(arxiv.httpx, "AsyncClient", client)
        assert await search_arxiv("q") == []
