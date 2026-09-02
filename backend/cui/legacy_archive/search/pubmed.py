"""PubMed search adapter — pure fetcher, neutral dict contract.

Built natively against NCBI's E-utilities (``esearch`` + ``efetch``) with
``httpx`` and stdlib ``xml.etree.ElementTree`` — no ``biopython`` / ``Bio.Entrez``,
no new dependency.

Two-step flow:

1. ``esearch.fcgi`` (JSON) -> a list of PMIDs (``esearchresult.idlist``).
2. ``efetch.fcgi`` (XML) -> the ``PubmedArticle`` records for those PMIDs.

NCBI politeness: when ``NCBI_EMAIL`` / ``NCBI_API_KEY`` are present in the
environment they are appended as ``email`` / ``api_key`` query params to BOTH
calls (the key raises the rate limit). Keyless still works at a lower rate. The
orchestrator's ``mailto`` kwarg is absorbed via ``**kw`` and ignored in favour
of ``NCBI_EMAIL``.

esearch is the rate-limited entry point, so it gets **exponential backoff**
mirroring ``arxiv.py`` exactly: on a 429/503 status or a transient request error
it retries up to 3 times with delays of 1s, 2s, 4s (via ``asyncio.sleep``). On
exhausting the retries, or on any other HTTP error / timeout / malformed
response, it degrades gracefully to ``[]``.

No domain imports, no module-global mutable state. ``map_pubmed_article`` is a
pure helper so tests/fixtures map without an HTTP round-trip.
"""

from __future__ import annotations

import asyncio
import logging
import os
from xml.etree import ElementTree as ET

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ESEARCH_URL = f"{BASE_URL}/esearch.fcgi"
EFETCH_URL = f"{BASE_URL}/efetch.fcgi"
TIMEOUT_SECONDS = 15.0

# Exponential backoff for NCBI's rate limiting (applied to esearch).
MAX_RETRIES = 3
BACKOFF_DELAYS = (1.0, 2.0, 4.0)  # seconds; index by (attempt - 1)
RETRY_STATUSES = frozenset({429, 503})


def _load_ncbi_credentials() -> tuple[str | None, str | None]:
    """Read optional ``NCBI_EMAIL`` / ``NCBI_API_KEY`` from env.

    Returns ``(email, api_key)``, each ``None`` when unset. When present they are
    appended to esearch/efetch as ``email`` / ``api_key`` query params (NCBI
    politeness; the key lifts the rate limit). Mirrors the ``load_dotenv()`` +
    ``os.getenv`` pattern used by ``semantic_scholar._load_api_key`` /
    ``collect_service._load_contact_email``.
    """
    load_dotenv()
    return os.getenv("NCBI_EMAIL") or None, os.getenv("NCBI_API_KEY") or None


def _ncbi_params(email: str | None, api_key: str | None) -> dict[str, object]:
    """Build the shared politeness params for esearch/efetch. Pure."""
    params: dict[str, object] = {}
    if email:
        params["email"] = email
    if api_key:
        params["api_key"] = api_key
    return params


def _text(elem: ET.Element | None) -> str:
    """Stripped text of an element, or "" when absent. Pure."""
    if elem is None or elem.text is None:
        return ""
    return elem.text.strip()


def _year_from_pubdate(pubdate: ET.Element | None) -> int | None:
    """Extract a 4-digit year from a ``PubDate`` element. Pure.

    Prefers the explicit ``<Year>`` child; falls back to the leading 4 digits of
    ``<MedlineDate>`` (e.g. "1998 Dec-1999 Jan" -> 1998).
    """
    if pubdate is None:
        return None
    year_text = _text(pubdate.find("Year"))
    if len(year_text) >= 4 and year_text[:4].isdigit():
        return int(year_text[:4])
    medline = _text(pubdate.find("MedlineDate"))
    if len(medline) >= 4 and medline[:4].isdigit():
        return int(medline[:4])
    return None


def _format_author(author: ET.Element) -> str:
    """Format one ``<Author>`` element -> "ForeName LastName". Pure.

    Falls back to LastName alone, then to a ``<CollectiveName>`` (group authors).
    Returns "" when nothing usable is present.
    """
    fore = _text(author.find("ForeName"))
    last = _text(author.find("LastName"))
    if fore and last:
        return f"{fore} {last}"
    if last:
        return last
    return _text(author.find("CollectiveName"))


def map_pubmed_article(elem: ET.Element) -> dict:
    """Map one ``<PubmedArticle>`` element -> the neutral paper-like dict.

    Pure (no I/O). Operates on a parsed ``xml.etree`` element.
    """
    citation = elem.find("MedlineCitation")
    article = citation.find("Article") if citation is not None else None

    pmid = _text(citation.find("PMID")) if citation is not None else ""

    title = _text(article.find("ArticleTitle")) if article is not None else ""

    # Abstract: there can be several <AbstractText> nodes (with Label attrs).
    # Concatenate their text; prefix structured labels (e.g. "BACKGROUND: ...").
    abstract_parts: list[str] = []
    if article is not None:
        for node in article.findall("Abstract/AbstractText"):
            text = "".join(node.itertext()).strip()
            if not text:
                continue
            label = node.get("Label")
            abstract_parts.append(f"{label}: {text}" if label else text)
    abstract = " ".join(abstract_parts)

    authors: list[str] = []
    if article is not None:
        for author in article.findall("AuthorList/Author"):
            name = _format_author(author)
            if name:
                authors.append(name)

    pubdate = (
        article.find("Journal/JournalIssue/PubDate")
        if article is not None
        else None
    )
    year = _year_from_pubdate(pubdate)

    venue = ""
    if article is not None:
        venue = _text(article.find("Journal/Title"))
        if not venue:
            venue = _text(article.find("Journal/ISOAbbreviation"))

    # DOI lives in the PubmedData/ArticleIdList with IdType="doi".
    doi = ""
    for article_id in elem.findall("PubmedData/ArticleIdList/ArticleId"):
        if article_id.get("IdType") == "doi":
            doi = _text(article_id)
            break

    return {
        "source": "pubmed",
        "source_id": pmid,
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "year": year,
        "venue": venue,
        "citations": 0,  # PubMed exposes no citation count
        "doi": doi,
        "pdf_urls": [],  # none available from E-utilities
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
    }


async def _esearch_pmids(
    client: httpx.AsyncClient,
    query: str,
    max_results: int,
    politeness: dict[str, object],
) -> list[str] | None:
    """Run esearch with exponential backoff; return PMIDs or ``None`` on failure.

    ``None`` signals "give up, return [] to the caller"; an empty list means a
    valid-but-empty result set.
    """
    params: dict[str, object] = {
        "db": "pubmed",
        "term": query,
        "retmax": min(max(max_results, 1), 100),
        "retmode": "json",
        **politeness,
    }

    attempt = 0
    while True:
        try:
            response = await client.get(ESEARCH_URL, params=params)
            if response.status_code in RETRY_STATUSES:
                if attempt < MAX_RETRIES:
                    delay = BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS) - 1)]
                    logger.warning(
                        "PubMed esearch %s for %r; backing off %.0fs "
                        "(attempt %d/%d)",
                        response.status_code, query, delay, attempt + 1, MAX_RETRIES,
                    )
                    await asyncio.sleep(delay)
                    attempt += 1
                    continue
                logger.warning("PubMed esearch retries exhausted for %r", query)
                return None
            response.raise_for_status()
            data = response.json()
            break
        except httpx.TransportError as exc:
            if attempt < MAX_RETRIES:
                delay = BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS) - 1)]
                logger.warning(
                    "PubMed esearch transient error for %r: %s; backing off "
                    "%.0fs (attempt %d/%d)",
                    query, exc, delay, attempt + 1, MAX_RETRIES,
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue
            logger.warning(
                "PubMed esearch retries exhausted (transport) for %r", query
            )
            return None
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("PubMed esearch failed for %r: %s", query, exc)
            return None

    idlist = ((data.get("esearchresult") or {}).get("idlist")) or []
    return [str(pmid) for pmid in idlist if pmid]


async def search_pubmed(
    query: str,
    max_results: int = 10,
    **_kw,
) -> list[dict]:
    """Search PubMed via E-utilities; return neutral paper-like dicts.

    Two HTTP calls (esearch -> efetch). esearch retries with exponential backoff
    (1s, 2s, 4s) on 429/503 or transient request errors, up to ``MAX_RETRIES``
    times. Returns ``[]`` on exhausted retries, an empty idlist, or any other
    HTTP error / timeout / malformed response. 15s timeout.

    ``NCBI_EMAIL`` / ``NCBI_API_KEY``, when set in the environment, are appended
    as ``email`` / ``api_key`` query params to both calls. The orchestrator's
    ``mailto`` kwarg is absorbed via ``**_kw`` and ignored.
    """
    email, api_key = _load_ncbi_credentials()
    politeness = _ncbi_params(email, api_key)

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            pmids = await _esearch_pmids(client, query, max_results, politeness)
            if pmids is None:
                return []
            if not pmids:
                return []

            fetch_params: dict[str, object] = {
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "xml",
                **politeness,
            }
            response = await client.get(EFETCH_URL, params=fetch_params)
            response.raise_for_status()
            body = response.text
    except httpx.HTTPError as exc:
        logger.warning("PubMed efetch failed for %r: %s", query, exc)
        return []

    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        logger.warning("PubMed XML parse failed for %r: %s", query, exc)
        return []

    papers: list[dict] = []
    for elem in root.findall("PubmedArticle"):
        papers.append(map_pubmed_article(elem))
        if len(papers) >= max_results:
            break
    return papers
