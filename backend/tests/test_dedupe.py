"""Tests for the pure dedupe of neutral paper dicts across sources."""

from __future__ import annotations

from anneal.search.dedupe import dedupe


def _paper(**kw) -> dict:
    base = {
        "source": "openalex",
        "source_id": "W1",
        "title": "A title",
        "authors": [],
        "abstract": "",
        "year": 2020,
        "venue": "",
        "citations": 0,
        "doi": "",
        "pdf_urls": [],
        "url": "",
    }
    base.update(kw)
    return base


class TestDedupeByDOI:
    def test_same_doi_merges_and_lists_both_sources(self):
        a = _paper(
            source="openalex", source_id="W1", doi="10.1/AbC",
            abstract="short", pdf_urls=["u1"], citations=5,
        )
        b = _paper(
            source="crossref", source_id="10.1/abc", doi="10.1/abc",
            abstract="a much longer richer abstract", pdf_urls=["u2"], citations=9,
        )

        out = dedupe([a, b])

        assert len(out) == 1
        merged = out[0]
        assert merged["sources"] == ["openalex", "crossref"]
        # primary source/source_id are first-seen
        assert merged["source"] == "openalex"
        assert merged["source_id"] == "W1"
        # richer (longer) abstract kept
        assert merged["abstract"] == "a much longer richer abstract"
        # pdf_urls unioned, order preserved
        assert merged["pdf_urls"] == ["u1", "u2"]
        # max citations
        assert merged["citations"] == 9

    def test_doi_normalized_case_and_whitespace(self):
        a = _paper(source="a", source_id="1", doi=" 10.1/X ")
        b = _paper(source="b", source_id="2", doi="10.1/x")
        out = dedupe([a, b])
        assert len(out) == 1
        assert out[0]["sources"] == ["a", "b"]

    def test_pdf_urls_deduped_within_union(self):
        a = _paper(source="a", source_id="1", doi="10.1/x", pdf_urls=["u1", "u2"])
        b = _paper(source="b", source_id="2", doi="10.1/x", pdf_urls=["u2", "u3"])
        out = dedupe([a, b])
        assert out[0]["pdf_urls"] == ["u1", "u2", "u3"]


class TestDedupeFallbacks:
    def test_no_doi_falls_back_to_source_id(self):
        a = _paper(source="arxiv", source_id="2001.1", doi="")
        b = _paper(source="arxiv", source_id="2001.1", doi="", abstract="longer")
        c = _paper(source="arxiv", source_id="2001.2", doi="")
        out = dedupe([a, b, c])
        assert len(out) == 2
        assert out[0]["abstract"] == "longer"

    def test_different_source_same_id_not_merged(self):
        # "source:source_id" includes the source name, so different sources
        # with the same id are distinct.
        a = _paper(source="arxiv", source_id="X", doi="")
        b = _paper(source="openalex", source_id="X", doi="")
        out = dedupe([a, b])
        assert len(out) == 2

    def test_no_doi_no_source_id_falls_back_to_title_year(self):
        a = _paper(source="a", source_id="", doi="", title="The  Grilled   Idea",
                   year=2020)
        b = _paper(source="b", source_id="", doi="", title="the grilled idea",
                   year=2020)
        out = dedupe([a, b])
        assert len(out) == 1
        assert out[0]["sources"] == ["a", "b"]

    def test_title_year_different_year_not_merged(self):
        a = _paper(source="a", source_id="", doi="", title="t", year=2020)
        b = _paper(source="b", source_id="", doi="", title="t", year=2021)
        out = dedupe([a, b])
        assert len(out) == 2


class TestDedupeOrdering:
    def test_first_appearance_order_preserved(self):
        a = _paper(source="a", source_id="A", doi="")
        b = _paper(source="b", source_id="B", doi="")
        c = _paper(source="c", source_id="C", doi="")
        out = dedupe([b, a, c])
        assert [p["source_id"] for p in out] == ["B", "A", "C"]

    def test_singleton_gets_sources_list(self):
        out = dedupe([_paper(source="openalex", source_id="W1")])
        assert out[0]["sources"] == ["openalex"]

    def test_empty_input(self):
        assert dedupe([]) == []
