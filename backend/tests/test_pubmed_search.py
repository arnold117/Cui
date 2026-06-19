"""Tests for the PubMed (NCBI E-utilities) search adapter.

Pure mapping, the two-call esearch -> efetch flow, graceful degradation, the
exponential-backoff retry path on esearch, and NCBI email/api_key politeness
params.

No real network: we monkeypatch ``httpx.AsyncClient`` with a fake whose ``get``
inspects the URL to decide whether it is answering esearch or efetch, and patch
``asyncio.sleep`` so backoff tests run instantly. An autouse fixture deletes any
real ``NCBI_*`` env and stubs ``load_dotenv`` so the suite is hermetic.
"""

from __future__ import annotations

import json
from xml.etree import ElementTree as ET

import httpx
import pytest

from anneal.search import pubmed
from anneal.search.pubmed import map_pubmed_article, search_pubmed


# esearch JSON returning two PMIDs.
SAMPLE_ESEARCH = json.dumps(
    {"esearchresult": {"count": "2", "idlist": ["111", "222"]}}
)

# efetch XML: article 111 has a structured (multi-node) abstract + a DOI;
# article 222 is minimal — no abstract, a MedlineDate (no <Year>), a collective
# author, and no DOI — to exercise the graceful fallbacks.
SAMPLE_EFETCH = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>111</PMID>
      <Article>
        <Journal>
          <Title>Journal of Forged Drafts</Title>
          <ISOAbbreviation>J. Forged Drafts</ISOAbbreviation>
          <JournalIssue>
            <PubDate><Year>2020</Year><Month>Jan</Month></PubDate>
          </JournalIssue>
        </Journal>
        <ArticleTitle>Annealing methods for adversarial writing engines</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">The grilled idea survives.</AbstractText>
          <AbstractText Label="RESULTS">Trajectory compounds.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><ForeName>Ada</ForeName><LastName>Lovelace</LastName></Author>
          <Author><ForeName>Alan</ForeName><LastName>Turing</LastName></Author>
        </AuthorList>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">111</ArticleId>
        <ArticleId IdType="doi">10.1234/abc.2020.42</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>222</PMID>
      <Article>
        <Journal>
          <Title>Minimalist Letters</Title>
          <JournalIssue>
            <PubDate><MedlineDate>1998 Dec-1999 Jan</MedlineDate></PubDate>
          </JournalIssue>
        </Journal>
        <ArticleTitle>A minimal record</ArticleTitle>
        <AuthorList>
          <Author><CollectiveName>The Anneal Collaboration</CollectiveName></Author>
          <Author><LastName>Solo</LastName></Author>
        </AuthorList>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">222</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            req = httpx.Request("GET", pubmed.BASE_URL)
            resp = httpx.Response(self.status_code, request=req)
            raise httpx.HTTPStatusError(
                str(self.status_code), request=req, response=resp
            )


def _two_call_client(esearch_responses, efetch_response):
    """Build a fake AsyncClient class.

    ``esearch_responses`` is the ordered sequence returned for esearch URLs
    (each a ``_FakeResponse`` or an Exception to raise — supports backoff
    sequences). ``efetch_response`` is the single response for the efetch URL.
    The fake inspects the request URL to decide which it is answering.
    """
    esearch_seq = list(esearch_responses)
    state = {"esearch_n": 0, "efetch_n": 0, "last_params": None, "urls": []}

    class _Client:
        def __init__(self, *a, **k) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> None:
            return None

        async def get(self, url, params=None):
            state["last_params"] = params
            state["urls"].append((url, params))
            if "esearch" in url:
                item = esearch_seq[state["esearch_n"]]
                state["esearch_n"] += 1
                if isinstance(item, Exception):
                    raise item
                return item
            # efetch
            state["efetch_n"] += 1
            if isinstance(efetch_response, Exception):
                raise efetch_response
            return efetch_response

    _Client.state = state
    return _Client


@pytest.fixture
def no_sleep(monkeypatch):
    """Patch asyncio.sleep so backoff is instant; record the delays used."""
    delays: list[float] = []

    async def fake_sleep(d):
        delays.append(d)

    monkeypatch.setattr(pubmed.asyncio, "sleep", fake_sleep)
    return delays


@pytest.fixture(autouse=True)
def _no_ncbi_env(monkeypatch):
    """Default: no NCBI creds in the environment (and don't read a real .env)."""
    monkeypatch.delenv("NCBI_EMAIL", raising=False)
    monkeypatch.delenv("NCBI_API_KEY", raising=False)
    monkeypatch.setattr(pubmed, "load_dotenv", lambda *a, **k: None)


def _first_article() -> ET.Element:
    root = ET.fromstring(SAMPLE_EFETCH)
    return root.findall("PubmedArticle")[0]


def _second_article() -> ET.Element:
    root = ET.fromstring(SAMPLE_EFETCH)
    return root.findall("PubmedArticle")[1]


class TestMapPubmedArticle:
    def test_maps_neutral_schema(self):
        d = map_pubmed_article(_first_article())

        assert d["source"] == "pubmed"
        assert d["source_id"] == "111"
        assert d["title"] == "Annealing methods for adversarial writing engines"
        assert d["authors"] == ["Ada Lovelace", "Alan Turing"]
        # Multi-node abstract joined, labels prefixed.
        assert d["abstract"] == (
            "BACKGROUND: The grilled idea survives. RESULTS: Trajectory compounds."
        )
        assert d["year"] == 2020
        assert d["venue"] == "Journal of Forged Drafts"
        assert d["citations"] == 0
        assert d["doi"] == "10.1234/abc.2020.42"
        assert d["pdf_urls"] == []
        assert d["url"] == "https://pubmed.ncbi.nlm.nih.gov/111/"

    def test_exact_schema_keys(self):
        d = map_pubmed_article(_first_article())
        assert set(d.keys()) == {
            "source", "source_id", "title", "authors", "abstract", "year",
            "venue", "citations", "doi", "pdf_urls", "url",
        }

    def test_minimal_article_graceful_fallbacks(self):
        d = map_pubmed_article(_second_article())
        assert d["source_id"] == "222"
        assert d["abstract"] == ""  # no AbstractText nodes
        assert d["doi"] == ""  # no doi ArticleId
        assert d["citations"] == 0
        assert d["pdf_urls"] == []
        # MedlineDate leading-year fallback.
        assert d["year"] == 1998

    def test_collective_and_lastname_only_authors(self):
        d = map_pubmed_article(_second_article())
        assert d["authors"] == ["The Anneal Collaboration", "Solo"]

    def test_venue_falls_back_to_iso_abbreviation(self):
        xml = """<PubmedArticle><MedlineCitation><PMID>9</PMID>
          <Article><Journal><ISOAbbreviation>Nat. AI</ISOAbbreviation>
          <JournalIssue><PubDate><Year>2021</Year></PubDate></JournalIssue>
          </Journal><ArticleTitle>t</ArticleTitle></Article>
          </MedlineCitation></PubmedArticle>"""
        d = map_pubmed_article(ET.fromstring(xml))
        assert d["venue"] == "Nat. AI"
        assert d["year"] == 2021


class TestSearchPubmed:
    async def test_maps_results(self, monkeypatch):
        client = _two_call_client(
            [_FakeResponse(200, SAMPLE_ESEARCH)],
            _FakeResponse(200, SAMPLE_EFETCH),
        )
        monkeypatch.setattr(pubmed.httpx, "AsyncClient", client)
        results = await search_pubmed("annealing", max_results=5)
        assert len(results) == 2
        assert results[0]["source_id"] == "111"
        assert results[1]["source_id"] == "222"

    async def test_esearch_sends_db_term_retmode(self, monkeypatch):
        client = _two_call_client(
            [_FakeResponse(200, SAMPLE_ESEARCH)],
            _FakeResponse(200, SAMPLE_EFETCH),
        )
        monkeypatch.setattr(pubmed.httpx, "AsyncClient", client)
        await search_pubmed("neural nets", max_results=3)
        esearch_url, esearch_params = client.state["urls"][0]
        assert "esearch" in esearch_url
        assert esearch_params["db"] == "pubmed"
        assert esearch_params["term"] == "neural nets"
        assert esearch_params["retmax"] == 3
        assert esearch_params["retmode"] == "json"
        # efetch sends the comma-joined PMID list.
        efetch_url, efetch_params = client.state["urls"][1]
        assert "efetch" in efetch_url
        assert efetch_params["id"] == "111,222"
        assert efetch_params["retmode"] == "xml"

    async def test_empty_idlist_returns_empty_and_skips_efetch(self, monkeypatch):
        empty = json.dumps({"esearchresult": {"idlist": []}})
        client = _two_call_client(
            [_FakeResponse(200, empty)],
            _FakeResponse(200, SAMPLE_EFETCH),
        )
        monkeypatch.setattr(pubmed.httpx, "AsyncClient", client)
        results = await search_pubmed("nothing")
        assert results == []
        assert client.state["efetch_n"] == 0  # never fetched

    async def test_esearch_http_error_returns_empty(self, monkeypatch):
        client = _two_call_client(
            [_FakeResponse(500, "")],
            _FakeResponse(200, SAMPLE_EFETCH),
        )
        monkeypatch.setattr(pubmed.httpx, "AsyncClient", client)
        assert await search_pubmed("q") == []
        assert client.state["efetch_n"] == 0

    async def test_esearch_malformed_json_returns_empty(self, monkeypatch):
        client = _two_call_client(
            [_FakeResponse(200, "{not json")],
            _FakeResponse(200, SAMPLE_EFETCH),
        )
        monkeypatch.setattr(pubmed.httpx, "AsyncClient", client)
        assert await search_pubmed("q") == []

    async def test_efetch_http_error_returns_empty(self, monkeypatch):
        client = _two_call_client(
            [_FakeResponse(200, SAMPLE_ESEARCH)],
            _FakeResponse(500, ""),
        )
        monkeypatch.setattr(pubmed.httpx, "AsyncClient", client)
        assert await search_pubmed("q") == []

    async def test_efetch_malformed_xml_returns_empty(self, monkeypatch):
        client = _two_call_client(
            [_FakeResponse(200, SAMPLE_ESEARCH)],
            _FakeResponse(200, "<not valid xml"),
        )
        monkeypatch.setattr(pubmed.httpx, "AsyncClient", client)
        assert await search_pubmed("q") == []


class TestBackoff:
    async def test_backoff_retries_then_succeeds(self, monkeypatch, no_sleep):
        client = _two_call_client(
            [
                _FakeResponse(429, ""),
                _FakeResponse(429, ""),
                _FakeResponse(200, SAMPLE_ESEARCH),
            ],
            _FakeResponse(200, SAMPLE_EFETCH),
        )
        monkeypatch.setattr(pubmed.httpx, "AsyncClient", client)
        results = await search_pubmed("annealing")
        assert len(results) == 2  # succeeded after retrying esearch
        assert client.state["esearch_n"] == 3  # two 429s + one success
        assert no_sleep == [1.0, 2.0]  # exponential delays for the 2 retries

    async def test_backoff_retries_on_503(self, monkeypatch, no_sleep):
        client = _two_call_client(
            [_FakeResponse(503, ""), _FakeResponse(200, SAMPLE_ESEARCH)],
            _FakeResponse(200, SAMPLE_EFETCH),
        )
        monkeypatch.setattr(pubmed.httpx, "AsyncClient", client)
        results = await search_pubmed("q")
        assert len(results) == 2
        assert no_sleep == [1.0]

    async def test_backoff_exhausted_returns_empty(self, monkeypatch, no_sleep):
        client = _two_call_client(
            [
                _FakeResponse(429, ""),
                _FakeResponse(429, ""),
                _FakeResponse(429, ""),
                _FakeResponse(429, ""),
            ],
            _FakeResponse(200, SAMPLE_EFETCH),
        )
        monkeypatch.setattr(pubmed.httpx, "AsyncClient", client)
        results = await search_pubmed("q")
        assert results == []
        assert no_sleep == [1.0, 2.0, 4.0]  # 3 retries before giving up

    async def test_transient_error_retries(self, monkeypatch, no_sleep):
        client = _two_call_client(
            [httpx.ConnectError("boom"), _FakeResponse(200, SAMPLE_ESEARCH)],
            _FakeResponse(200, SAMPLE_EFETCH),
        )
        monkeypatch.setattr(pubmed.httpx, "AsyncClient", client)
        results = await search_pubmed("q")
        assert len(results) == 2
        assert no_sleep == [1.0]

    async def test_non_retryable_http_error_not_retried(self, monkeypatch, no_sleep):
        client = _two_call_client(
            [_FakeResponse(500, "")],
            _FakeResponse(200, SAMPLE_EFETCH),
        )
        monkeypatch.setattr(pubmed.httpx, "AsyncClient", client)
        assert await search_pubmed("q") == []
        assert no_sleep == []  # 500 is not retried


class TestNcbiCredentials:
    async def test_email_and_api_key_appended_when_set(self, monkeypatch):
        monkeypatch.setenv("NCBI_EMAIL", "me@example.com")
        monkeypatch.setenv("NCBI_API_KEY", "secret-key")
        client = _two_call_client(
            [_FakeResponse(200, SAMPLE_ESEARCH)],
            _FakeResponse(200, SAMPLE_EFETCH),
        )
        monkeypatch.setattr(pubmed.httpx, "AsyncClient", client)
        await search_pubmed("q")
        # Both calls carry the politeness params.
        for _url, params in client.state["urls"]:
            assert params["email"] == "me@example.com"
            assert params["api_key"] == "secret-key"

    async def test_params_absent_when_unset(self, monkeypatch):
        # _no_ncbi_env autouse fixture already cleared the env.
        client = _two_call_client(
            [_FakeResponse(200, SAMPLE_ESEARCH)],
            _FakeResponse(200, SAMPLE_EFETCH),
        )
        monkeypatch.setattr(pubmed.httpx, "AsyncClient", client)
        await search_pubmed("q")
        for _url, params in client.state["urls"]:
            assert "email" not in params
            assert "api_key" not in params

    async def test_mailto_kwarg_absorbed_not_used(self, monkeypatch):
        # The orchestrator passes mailto=; it must be ignored (NCBI_EMAIL wins).
        client = _two_call_client(
            [_FakeResponse(200, SAMPLE_ESEARCH)],
            _FakeResponse(200, SAMPLE_EFETCH),
        )
        monkeypatch.setattr(pubmed.httpx, "AsyncClient", client)
        results = await search_pubmed("q", mailto="orchestrator@example.com")
        assert len(results) == 2
        for _url, params in client.state["urls"]:
            assert "mailto" not in params
            assert "email" not in params  # NCBI_EMAIL unset -> no email param
