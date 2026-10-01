"""dialogue_sources: normalization + degradation behavior (arXiv throttled)."""
import asyncio
import time

from cui.research_universe import dialogue_sources as ds


def test_normalise_canonicalises_openalex_arxiv_doi():
    item = ds._normalise({
        "title": "Some paper", "abstract": "An abstract body.",
        "source": "openalex", "url": "https://doi.org/10.48550/arxiv.2301.12345v2",
        "doi": "10.48550/arxiv.2301.12345v2",
    })
    assert item is not None
    assert item["locator"] == "arxiv:2301.12345"


def test_normalise_keeps_real_doi():
    item = ds._normalise({
        "title": "Some paper", "abstract": "An abstract body.",
        "source": "openalex", "url": "https://doi.org/10.1000/xyz123",
        "doi": "10.1000/xyz123",
    })
    assert item is not None
    assert item["locator"] == "doi:10.1000/xyz123"


def test_external_search_does_not_stall_on_throttled_arxiv(monkeypatch):
    async def slow_arxiv(query, max_results):
        await asyncio.sleep(30)
        return []

    async def canned_openalex(query, max_results):
        return [{"title": "OpenAlex paper", "abstract": "An abstract about long context.", "source": "openalex",
                 "url": "https://doi.org/10.48550/arxiv.2406.00001", "doi": "10.48550/arxiv.2406.00001"}]

    monkeypatch.setattr(ds, "ARXIV_WALL_SECONDS", 0.1)
    monkeypatch.setattr(ds, "search_arxiv", slow_arxiv)
    monkeypatch.setattr(ds, "search_openalex", canned_openalex)
    started = time.monotonic()
    items = asyncio.run(ds.external_search("long context", per_source=3))
    elapsed = time.monotonic() - started
    assert elapsed < 5, f"arXiv leg stalled the search: {elapsed:.1f}s"
    assert [i["locator"] for i in items] == ["arxiv:2406.00001"]
    assert items[0]["source"] == "openalex"


# --- real fetcher mapper output (no network) ---------------------------------
import xml.etree.ElementTree as ET  # noqa: E402

from cui.legacy_archive.search.arxiv import map_arxiv  # noqa: E402
from cui.legacy_archive.search.openalex import map_work  # noqa: E402


def _arxiv_entry(doi: str = "") -> dict:
    doi_xml = f"<arxiv:doi>{doi}</arxiv:doi>" if doi else ""
    xml = (
        '<entry xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">'
        "<id>http://arxiv.org/abs/2401.01234v2</id><title>Arx  paper</title>"
        "<summary>An abstract body.</summary><published>2024-01-15T00:00:00Z</published>"
        '<author><name>A B</name></author><category term="cs.CL"/>'
        '<link href="http://arxiv.org/abs/2401.01234v2" rel="alternate"/>'
        '<link title="pdf" href="http://arxiv.org/pdf/2401.01234v2" rel="related" type="application/pdf"/>'
        f"{doi_xml}</entry>"
    )
    return map_arxiv(ET.fromstring(xml))


def _work(doi: str | None = None) -> dict:
    return map_work({
        "id": "https://openalex.org/W123", "display_name": "OA paper", "doi": doi,
        "abstract_inverted_index": {"An": [0], "abstract": [1]}, "publication_year": 2023,
        "locations": [{"pdf_url": "https://example.org/a.pdf"}],
    })


def test_arxiv_hit_without_doi_gets_arxiv_locator():
    item = ds._normalise(_arxiv_entry())
    assert item is not None and item["locator"] == "arxiv:2401.01234"


def test_arxiv_hit_with_arxiv_doi():
    item = ds._normalise(_arxiv_entry("10.48550/arXiv.2401.01234"))
    assert item is not None and item["locator"] == "arxiv:2401.01234"


def test_two_arxiv_hits_without_doi_both_survive_dedupe(monkeypatch):
    other = _arxiv_entry() | {"source_id": "2402.99999", "title": "Other"}

    async def arx(query, max_results):
        return [_arxiv_entry(), other]

    async def oa(query, max_results):
        return []

    monkeypatch.setattr(ds, "search_arxiv", arx)
    monkeypatch.setattr(ds, "search_openalex", oa)
    items = asyncio.run(ds.external_search("q"))
    assert [i["locator"] for i in items] == ["arxiv:2401.01234", "arxiv:2402.99999"]


def test_openalex_hit_without_doi_gets_openalex_locator():
    item = ds._normalise(_work())
    assert item is not None and item["locator"] == "openalex:W123"


def test_openalex_hit_with_doi():
    item = ds._normalise(_work("https://doi.org/10.1000/XYZ"))
    assert item is not None and item["locator"] == "doi:10.1000/xyz"


def test_pdf_url_falls_back_when_no_url():
    item = ds._normalise(_work() | {"url": ""})
    assert item is not None and item["url"] == "https://example.org/a.pdf"


def test_no_derivable_id_never_emits_empty_locator():
    item = ds._normalise(_arxiv_entry() | {"source_id": "", "url": ""})
    assert item is None or item["locator"] not in ("arxiv:", "")
    assert ds._normalise(_work() | {"source_id": "", "url": ""}) is None
