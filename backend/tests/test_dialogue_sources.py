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
