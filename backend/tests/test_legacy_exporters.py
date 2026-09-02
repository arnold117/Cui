"""Tests for the v4 exporters port (T6 item 3; legacy_archive.exporters).

Pure input → pure assertion, fully offline (no subprocess, no network, no
filesystem): BibTeX key/value escaping and entry assembly, cite-key generation,
entry-type detection, citation author strings + full citations across the five
styles, and the pandoc argument/document builders (execution stays with
slice1/the caller by design). Expected strings encode v4 behavior verbatim.
"""

from __future__ import annotations

import pytest

from cui.legacy_archive.exporters import (
    CitationStyle,
    ExportConfig,
    ExportFormat,
    PaperLike,
    build_markdown,
    build_pandoc_command,
    detect_entry_type,
    escape_bibtex,
    format_authors_apa,
    format_authors_chicago,
    format_authors_gbt7714,
    format_authors_ieee,
    format_authors_mla,
    format_citation,
    format_citations,
    generate_cite_key,
    normalize_author_name,
    papers_to_bibtex,
    resolve_output_path,
)
from cui.legacy_archive.exporters.bibtex import BibTeXEntry

P = PaperLike


def paper(**overrides) -> PaperLike:
    """Minimal paper-like fixture; overridable per test."""
    base = dict(
        paper_id="p1",
        title="Deep Learning",
        authors=["John Smith"],
        abstract="",
        year=2020,
        sources={},
        venue="",
        doi="",
    )
    base.update(overrides)
    return P(**base)


class TestEscapeBibtex:
    def test_escapes_special_chars(self) -> None:
        assert (
            escape_bibtex("Rock & Roll 100% $5 #1 a_b {c}")
            == r"Rock \& Roll 100\% \$5 \#1 a\_b \{c\}"
        )

    def test_tilde_and_caret(self) -> None:
        assert escape_bibtex("a~b^c") == r"a\textasciitilde{}b\textasciicircum{}c"

    def test_already_escaped_left_alone(self) -> None:
        assert escape_bibtex(r"\& and \_x") == r"\& and \_x"

    def test_empty_string(self) -> None:
        assert escape_bibtex("") == ""


class TestNormalizeAuthorName:
    def test_two_parts_flips_to_last_first(self) -> None:
        assert normalize_author_name("John Smith") == "Smith, John"

    def test_already_last_first_unchanged(self) -> None:
        assert normalize_author_name("Smith, John") == "Smith, John"

    def test_single_token_unchanged(self) -> None:
        assert normalize_author_name("Aristotle") == "Aristotle"

    def test_multi_given_names(self) -> None:
        assert normalize_author_name("John Ronald Tolkien") == "Tolkien, John Ronald"

    def test_strips_whitespace(self) -> None:
        assert normalize_author_name("  John   Smith  ") == "Smith, John"


class TestGenerateCiteKey:
    def test_basic_format(self) -> None:
        assert (
            generate_cite_key(["Smith, John"], 2023, "Deep Learning for NLP")
            == "smith2023deep"
        )

    def test_skips_stop_words_in_title(self) -> None:
        assert (
            generate_cite_key(["Smith, John"], 2023, "The Art of Deep Learning")
            == "smith2023art"
        )

    def test_all_stop_words_falls_back_to_paper(self) -> None:
        assert (
            generate_cite_key(["Smith, John"], 2023, "In Of The For To With")
            == "smith2023paper"
        )

    def test_single_initial_last_token_uses_first_word(self) -> None:
        # "Hinton E" — trailing token is a one-letter initial → last name first
        assert (
            generate_cite_key(["Hinton E"], 1986, "Learning Representations")
            == "hinton1986learning"
        )

    def test_ascii_normalization_of_accented_names(self) -> None:
        assert (
            generate_cite_key(["García, José"], 2024, "Metaphors")
            == "garcia2024metaphors"
        )

    def test_no_authors_yields_unknown(self) -> None:
        assert generate_cite_key([], 2020, "The World") == "unknown2020world"

    def test_falsy_year_yields_xxxx(self) -> None:
        assert (
            generate_cite_key(["Smith, John"], 0, "Deep Learning")
            == "smithxxxxdeep"
        )

    def test_key_is_lowercased(self) -> None:
        assert (
            generate_cite_key(["Smith, John"], 2024, "DEEP LEARNING")
            == "smith2024deep"
        )


class TestDetectEntryType:
    def test_conference_venue(self) -> None:
        assert detect_entry_type("Proceedings of NeurIPS 2023") == "inproceedings"
        assert detect_entry_type("ICLR 2024 Conference") == "inproceedings"

    def test_journal_venue(self) -> None:
        assert (
            detect_entry_type("Journal of Machine Learning Research") == "article"
        )
        assert (
            detect_entry_type("IEEE Transactions on Pattern Analysis") == "article"
        )

    def test_nature(self) -> None:
        assert detect_entry_type("Nature") == "article"

    def test_arxiv_and_unknown_fall_to_misc(self) -> None:
        assert detect_entry_type("arXiv preprint arXiv:2301.00001") == "misc"
        assert detect_entry_type("Some Random Venue") == "misc"
        assert detect_entry_type("") == "misc"


class TestPapersToBibtex:
    def test_single_article_entry_full_document(self) -> None:
        p1 = paper(
            paper_id="10.1000/xyz",  # no doi field → DOI falls back to paper_id
            title="Deep Learning & Society",
            authors=["John Smith", "Jane Doe"],
            abstract="We study 100% of cases.",
            year=2024,
            venue="Journal of AI",
        )
        expected = "\n".join(
            [
                "% BibTeX bibliography generated by LitScribe",
                "% Contains 1 entries",
                "%",
                "% Citation keys follow the format: AuthorYearFirstword",
                "% e.g., smith2023deep for 'Deep Learning for NLP' by Smith (2023)",
                "",
                "@article{smith2024deep,",
                r"  title = {Deep Learning \& Society},",
                "  author = {Smith, John and Doe, Jane},",
                "  year = {2024},",
                r"  abstract = {We study 100\% of cases.},",
                "  journal = {Journal of AI},",
                "  doi = {10.1000/xyz},",
                "}",
                "",
            ]
        )
        assert papers_to_bibtex([p1]) == expected

    def test_unique_key_suffix_and_arxiv_inproceedings_fields(self) -> None:
        p1 = paper(paper_id="10.1000/xyz", title="Deep Learning & Society", year=2024)
        p2 = paper(
            paper_id="abc",
            title="Deep Learning in the Wild",
            authors=["John Smith"],
            year=2024,
            venue="Proceedings of NeurIPS 2023",
            sources={"arxiv": "2301.00001"},
        )
        bib = papers_to_bibtex([p1, p2])
        assert "@misc{smith2024deep," in bib  # p1: empty venue -> misc
        assert "@inproceedings{smith2024deepa," in bib  # duplicate key suffixed
        assert "  eprint = {2301.00001}," in bib
        assert "  archiveprefix = {arXiv}," in bib
        assert "  booktitle = {Proceedings of NeurIPS 2023}," in bib
        assert "@article{smith2024deepa" not in bib

    def test_doi_field_wins_over_paper_id(self) -> None:
        p = paper(paper_id="not-a-doi", doi="10.9999/real", year=2024)
        bib = papers_to_bibtex([p])
        assert "  doi = {10.9999/real}," in bib
        assert "not-a-doi" not in bib

    def test_empty_list_header(self) -> None:
        expected = "\n".join(
            [
                "% BibTeX bibliography generated by LitScribe",
                "% Contains 0 entries",
                "%",
                "% Citation keys follow the format: AuthorYearFirstword",
                "% e.g., smith2023deep for 'Deep Learning for NLP' by Smith (2023)",
                "",
            ]
        )
        assert papers_to_bibtex([]) == expected

    def test_entry_to_bibtex_skips_empty_fields(self) -> None:
        entry = BibTeXEntry(
            entry_type="misc",
            cite_key="k2020x",
            fields={"title": "X", "author": "", "note": ""},
        )
        assert entry.to_bibtex() == "@misc{k2020x,\n  title = {X},\n}"


class TestAuthorFormatters:
    def test_apa_single_and_pair(self) -> None:
        assert format_authors_apa(["John Smith"]) == "Smith, J."
        assert format_authors_apa(["Smith, John", "Doe, Jane"]) == (
            "Smith, J., & Doe, J."
        )

    def test_apa_many_and_ellipsis_rule(self) -> None:
        names = ["Alan Zeta"] * 21
        names[19] = "Nineteen Distinct"
        result = format_authors_apa(names)
        assert result.startswith("Zeta, A.")
        assert result.endswith("Zeta, A.")
        assert ", ... " in result
        assert "Distinct" not in result  # author #20 of 21 is the one ellipsized out
        assert "&" not in result

    def test_apa_twenty_all_listed(self) -> None:
        names = ["Alan Zeta"] * 20
        assert format_authors_apa(names).endswith(", & Zeta, A.")

    def test_apa_empty(self) -> None:
        assert format_authors_apa([]) == ""

    def test_mla_single_two_and_et_al(self) -> None:
        assert format_authors_mla(["Smith, John"]) == "Smith, John"
        assert format_authors_mla(["Turing, Alan", "John Smith"]) == (
            "Turing, Alan, and John Smith"
        )
        assert format_authors_mla(["Turing, Alan", "Smith, John", "Doe, Jane"]) == (
            "Turing, Alan, et al."
        )

    def test_ieee_formats(self) -> None:
        assert format_authors_ieee(["John Smith"]) == "J. Smith"
        assert format_authors_ieee(["John Ronald Tolkien"]) == "J. R. Tolkien"
        assert format_authors_ieee(["John Smith", "Jane Doe"]) == (
            "J. Smith and J. Doe"
        )
        assert format_authors_ieee(["John Smith", "Jane Doe", "Alan Turing"]) == (
            "J. Smith, J. Doe, and A. Turing"
        )

    def test_chicago_single_two_three_four(self) -> None:
        assert format_authors_chicago(["Turing, Alan"]) == "Turing, Alan"
        assert format_authors_chicago(["Turing, Alan", "Smith, John"]) == (
            "Turing, Alan, and John Smith"
        )
        assert format_authors_chicago(
            ["Turing, Alan", "Smith, John", "Doe, Jane"]
        ) == ("Turing, Alan, John Smith, and Jane Doe")
        assert format_authors_chicago(
            ["Turing, Alan", "Smith, John", "Doe, Jane", "Roe, Jim"]
        ) == "Turing, Alan, et al."

    def test_gbt7714_cap_and_ellipsis(self) -> None:
        assert format_authors_gbt7714(["张三", "李四", "王五"]) == "张三, 李四, 王五"
        assert format_authors_gbt7714(["张三", "李四", "王五", "赵六"]) == (
            "张三, 李四, 王五, 等"
        )
        assert format_authors_gbt7714(["a", "b", "c", "d"], max_authors=2) == "a, b, 等"


class TestCitationStrings:
    def test_apa_full_with_doi(self) -> None:
        p = paper(
            authors=["John Smith", "Jane Doe"],
            venue="Journal of AI",
            doi="10.1234/nlp",
        )
        assert format_citation(p, CitationStyle.APA) == (
            "Smith, J., & Doe, J. (2020). Deep Learning. "
            "*Journal of AI*. https://doi.org/10.1234/nlp"
        )

    def test_apa_arxiv_link_fallback(self) -> None:
        p = paper(venue="Journal of AI", sources={"arxiv": "2301.00001"})
        assert format_citation(p, CitationStyle.APA).endswith(
            "https://arxiv.org/abs/2301.00001"
        )

    def test_apa_no_year_no_venue_no_doi(self) -> None:
        p = paper(year=0)
        assert format_citation(p, CitationStyle.APA) == (
            "Smith, J. (n.d.). Deep Learning."
        )

    def test_apa_no_authors(self) -> None:
        p = paper(authors=[], year=2020)
        assert format_citation(p, CitationStyle.APA) == "(2020). Deep Learning."

    def test_mla_single_with_venue(self) -> None:
        p = paper(authors=["Smith, John"], venue="Journal of AI")
        assert format_citation(p, CitationStyle.MLA) == (
            'Smith, John. "Deep Learning." *Journal of AI*, 2020.'
        )

    def test_mla_single_without_venue(self) -> None:
        p = paper(authors=["Smith, John"])
        assert format_citation(p, CitationStyle.MLA) == (
            'Smith, John. "Deep Learning." 2020.'
        )

    def test_ieee_numbered_citation(self) -> None:
        p = paper(authors=["John Smith"], venue="IEEE Transactions on AI")
        assert format_citation(p, CitationStyle.IEEE) == (
            'J. Smith, "Deep Learning," *IEEE Transactions on AI*, 2020.'
        )
        numbered = format_citations([p], CitationStyle.IEEE)
        assert numbered == [
            '[1] J. Smith, "Deep Learning," *IEEE Transactions on AI*, 2020.'
        ]

    def test_ieee_no_year_terminates_last_part(self) -> None:
        p = paper(authors=["John Smith"], venue="IEEE Transactions on AI", year=0)
        assert format_citations([p], CitationStyle.IEEE) == [
            '[1] J. Smith, "Deep Learning," *IEEE Transactions on AI*.'
        ]

    def test_chicago_two_authors(self) -> None:
        p = paper(
            authors=["Turing, Alan", "Smith, John"],
            title="Deep Learning",
            venue="Modern History Review",
        )
        assert format_citation(p, CitationStyle.CHICAGO) == (
            'Turing, Alan, and John Smith. 2020. "Deep Learning." '
            "*Modern History Review*."
        )

    def test_chicago_single_author(self) -> None:
        p = paper(authors=["Turing, Alan"], venue="Press")
        assert format_citation(p, CitationStyle.CHICAGO) == (
            'Turing, Alan. 2020. "Deep Learning." *Press*.'
        )

    def test_gbt7714_proceedings_numbered(self) -> None:
        p = paper(
            paper_id="c1",
            title="深度学习研究",
            authors=["张三", "李四", "王五"],
            venue="Proceedings of ICML",
            year=2020,
        )
        assert format_citation(p, CitationStyle.GB_T_7714) == (
            "张三, 李四, 王五. 深度学习研究[C]. Proceedings of ICML, 2020."
        )
        assert format_citations([p], CitationStyle.GB_T_7714) == [
            "[1] 张三, 李四, 王五. 深度学习研究[C]. Proceedings of ICML, 2020."
        ]

    def test_gbt7714_journal_and_arxiv_doc_types(self) -> None:
        journal = paper(title="某研究", authors=["张三"], venue="Nature", year=2023)
        assert format_citation(journal, CitationStyle.GB_T_7714) == (
            "张三. 某研究[J]. Nature, 2023."
        )
        arxiv = paper(
            title="某预印本",
            authors=["张三"],
            year=2024,
            sources={"arxiv": "2401.00001"},
        )
        assert format_citation(arxiv, CitationStyle.GB_T_7714) == (
            "张三. 某预印本[EB/OL]. 2024."
        )

    def test_numbering_only_for_ieee_and_gbt7714(self) -> None:
        apa = format_citations([paper()], CitationStyle.APA)
        assert apa == ["Smith, J. (2020). Deep Learning."]
        chicago = format_citations([paper()], CitationStyle.CHICAGO)
        assert chicago == ['Smith, John. 2020. "Deep Learning."']


class TestBuildMarkdown:
    def test_full_document_golden(self) -> None:
        p = paper(venue="Journal of AI", doi="10.1234/nlp")
        config = ExportConfig(
            title="My Review",
            author="Arnold",
            date="2026-09-03",
        )
        expected = "\n".join(
            [
                "---",
                'title: "My Review"',
                'author: "Arnold"',
                'date: "2026-09-03"',
                "lang: en",
                "toc: true",
                "toc-depth: 3",
                "numbersections: true",
                "---",
                "",
                "Body paragraph one.",
                "",
                "# References",
                "",
                "Smith, J. (2020). Deep Learning. *Journal of AI*. "
                "https://doi.org/10.1234/nlp",
                "",
            ]
        )
        assert build_markdown("Body paragraph one.", [p], config) == expected

    def test_zh_pdf_adds_lang_font_and_geometry(self) -> None:
        config = ExportConfig(
            format=ExportFormat.PDF,
            language="zh",
            date="2026-09-03",
        )
        md = build_markdown("正文内容", [], config)
        assert "lang: zh-CN" in md
        assert 'CJKmainfont: "PingFang SC"' in md
        assert "fontsize: 11pt" in md
        assert "geometry: margin=1in" in md
        assert "# References" not in md  # no papers → no references section
        assert "# 参考文献" not in md

    def test_zh_references_heading_and_ieee_numbering(self) -> None:
        config = ExportConfig(
            language="zh",
            citation_style=CitationStyle.IEEE,
            date="2026-09-03",
        )
        md = build_markdown("正文", [paper()], config)
        assert "# 参考文献" in md
        assert '[1] J. Smith, "Deep Learning," 2020.' in md

    def test_toc_and_numbersections_off(self) -> None:
        config = ExportConfig(
            include_toc=False,
            number_sections=False,
            date="2026-09-03",
        )
        md = build_markdown("body", [], config)
        assert "toc: true" not in md
        assert "numbersections: true" not in md

    def test_references_omitted_when_disabled(self) -> None:
        config = ExportConfig(
            include_references=False,
            date="2026-09-03",
        )
        md = build_markdown("body", [paper()], config)
        assert "# References" not in md


class TestResolveOutputPath:
    def test_appends_missing_extension(self) -> None:
        assert str(resolve_output_path("report", ExportFormat.DOCX)) == "report.docx"

    def test_replaces_wrong_extension(self) -> None:
        assert str(resolve_output_path("report.pdf", ExportFormat.DOCX)) == (
            "report.docx"
        )

    def test_markdown_extension(self) -> None:
        assert str(resolve_output_path("review", ExportFormat.MARKDOWN)) == (
            "review.md"
        )


class TestBuildPandocCommand:
    def test_docx_base(self) -> None:
        cmd = build_pandoc_command(
            "review.md", "report.docx", ExportConfig(format=ExportFormat.DOCX)
        )
        assert cmd == ["pandoc", "review.md", "-o", "report.docx"]

    def test_bibliography_flags(self) -> None:
        cmd = build_pandoc_command(
            "review.md",
            "report.docx",
            ExportConfig(format=ExportFormat.DOCX),
            bibliography_path="refs.bib",
        )
        assert cmd == [
            "pandoc", "review.md", "-o", "report.docx",
            "--bibliography", "refs.bib", "--citeproc",
        ]

    def test_pdf_engine_and_zh_font(self) -> None:
        en = build_pandoc_command(
            "review.md", "out.pdf", ExportConfig(format=ExportFormat.PDF)
        )
        assert "--pdf-engine=xelatex" in en
        assert "CJKmainfont" not in en

        zh = build_pandoc_command(
            "review.md",
            "out.pdf",
            ExportConfig(format=ExportFormat.PDF, language="zh"),
        )
        assert zh[-2:] == ["-V", "CJKmainfont=PingFang SC"]
        assert "--pdf-engine=xelatex" in zh

    def test_docx_reference_template(self) -> None:
        cmd = build_pandoc_command(
            "review.md",
            "report.docx",
            ExportConfig(
                format=ExportFormat.DOCX, template="/templates/custom.docx"
            ),
        )
        assert "--reference-doc" in cmd
        assert cmd[-2:] == ["--reference-doc", "/templates/custom.docx"]

    def test_html_standalone_with_bib_and_extra_args(self) -> None:
        cmd = build_pandoc_command(
            "review.md",
            "out.html",
            ExportConfig(
                format=ExportFormat.HTML,
                extra_args=["--verbose"],
            ),
            bibliography_path="refs.bib",
        )
        assert cmd == [
            "pandoc", "review.md", "-o", "out.html",
            "--bibliography", "refs.bib", "--citeproc",
            "--standalone", "--self-contained",
            "--verbose",
        ]

    def test_markdown_format_rejected(self) -> None:
        with pytest.raises(ValueError):
            build_pandoc_command(
                "review.md",
                "out.md",
                ExportConfig(format=ExportFormat.MARKDOWN),
            )
