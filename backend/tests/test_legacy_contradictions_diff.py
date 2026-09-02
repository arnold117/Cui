"""Unit tests for the T6 item 5 ports: ``cui.legacy_archive.contradictions``
and ``cui.legacy_archive.diff`` (v4 LitScribe pure logic, semantics-verbatim).

Fully offline and deterministic: stdlib only, no I/O, no database, no LLM.
Assertions pin the v4-verbatim behaviors (including its quirks — un-stripped
claim text, difflib header details) so a later "cleaning" cannot silently
drift from what slice1 consumers expect of the archive.
"""

from __future__ import annotations

from cui.legacy_archive.contradictions import (
    Contradiction,
    ContradictionReport,
    extract_cited_claims,
    format_contradictions_for_synthesis,
)
from cui.legacy_archive.diff import colored_diff, diff_stats, html_diff, unified_diff

ESC = "\x1b"

# --- extract_cited_claims ---------------------------------------------------

SAMPLE_REVIEW = (
    "The first study reports that the new cooling method cut energy use by half "
    "across all seasons [@alpha12]. "
    "The second study found that the same cooling method raised energy use under "
    "tropical conditions [@beta7]. "
    "Short [@zeta]. "
    "Uncited sentence with nothing to see."
)

SAMPLE_EXPECTED = [
    (
        "The first study reports that the new cooling method cut energy use by half "
        "across all seasons ",
        "alpha12",
    ),
    # v4 quirk kept: the run starts right after the previous sentence's period,
    # so the inter-sentence space survives into the matched claim text.
    (
        " The second study found that the same cooling method raised energy use under "
        "tropical conditions ",
        "beta7",
    ),
]


def test_extract_cited_claims_matches_sentence_tail_before_marker():
    assert extract_cited_claims(SAMPLE_REVIEW) == SAMPLE_EXPECTED
    # markers preceded by < 20 chars (or inside an uncited sentence) do not match
    keys = [key for _, key in SAMPLE_EXPECTED]
    assert "zeta" not in keys


def test_extract_cited_claims_max_claims_cap():
    assert extract_cited_claims(SAMPLE_REVIEW, max_claims=1) == [SAMPLE_EXPECTED[0]]
    assert extract_cited_claims(SAMPLE_REVIEW, max_claims=0) == []
    assert extract_cited_claims("") == []


def test_extract_cited_claims_truncates_runs_longer_than_200():
    # a 250-char run before the marker is greedily cut to its trailing 200 chars
    assert extract_cited_claims("z" * 250 + "[@longkey].") == [("z" * 200, "longkey")]


def test_extract_cited_claims_requires_at_least_20_chars_and_word_key():
    assert extract_cited_claims("z" * 20 + "[@k].") == [("z" * 20, "k")]
    assert extract_cited_claims("z" * 19 + "[@k].") == []
    assert extract_cited_claims("some long enough claim text right here [@k-2] tail.") == []
    assert extract_cited_claims("No citation at all in this sentence.") == []


# --- Contradiction / ContradictionReport ------------------------------------

def test_contradiction_dataclass_carries_all_v4_fields():
    c = Contradiction(
        paper_a_id="pa1",
        paper_b_id="pb2",
        claim_a="claim from A",
        claim_b="claim from B",
        contradiction_type="methodological",
        explanation="same method, opposite results",
        severity="major",
    )
    assert c.paper_a_id == "pa1"
    assert c.paper_b_id == "pb2"
    assert c.claim_a == "claim from A"
    assert c.claim_b == "claim from B"
    assert c.contradiction_type == "methodological"
    assert c.explanation == "same method, opposite results"
    assert c.severity == "major"


def test_contradiction_report_count_and_defaults():
    empty = ContradictionReport()
    assert empty.total_pairs_checked == 0
    assert empty.contradictions == []
    assert empty.count == 0

    filled = ContradictionReport(
        total_pairs_checked=3,
        contradictions=[
            Contradiction("pa", "pb", "a1", "b1", "opposing_conclusions", "e1", "minor"),
            Contradiction("pa", "pc", "a2", "c2", "data_inconsistency", "e2", "moderate"),
        ],
    )
    assert filled.total_pairs_checked == 3
    assert filled.count == 2


# --- format_contradictions_for_synthesis -------------------------------------

def test_format_empty_report_returns_empty_string():
    assert format_contradictions_for_synthesis(ContradictionReport()) == ""


def test_format_renders_single_item_with_raw_ids():
    report = ContradictionReport(
        total_pairs_checked=1,
        contradictions=[
            Contradiction(
                paper_a_id="pa123",
                paper_b_id="pb456",
                claim_a="Drug X reduces symptoms",
                claim_b="Drug X worsens symptoms",
                contradiction_type="opposing_conclusions",
                explanation="Directly opposite effects on the same endpoint.",
                severity="major",
            )
        ],
    )
    assert format_contradictions_for_synthesis(report) == (
        "## Notable Contradictions in the Literature\n"
        "\n"
        '1. **Opposing Conclusions** (major): [@pa123] reports: "Drug X reduces '
        'symptoms", while [@pb456] finds: "Drug X worsens symptoms". Directly '
        "opposite effects on the same endpoint."
    )


def test_format_with_key_map_substitutes_paper_ids():
    report = ContradictionReport(
        contradictions=[
            Contradiction(
                paper_a_id="pa123",
                paper_b_id="pb456",
                claim_a="A says X",
                claim_b="B says not-X",
                contradiction_type="opposing_conclusions",
                explanation="conflict",
                severity="minor",
            )
        ]
    )
    out = format_contradictions_for_synthesis(report, key_map={"pa123": "alpha", "pb456": "beta"})
    assert "[@alpha] reports: \"A says X\"" in out
    assert "[@beta] finds: \"B says not-X\"" in out
    assert "pa123" not in out
    assert "pb456" not in out


def test_format_numbers_multiple_items():
    report = ContradictionReport(
        contradictions=[
            Contradiction("a", "b", "c1", "c2", "opposing_conclusions", "e1", "minor"),
            Contradiction("a", "c", "c3", "c4", "data_inconsistency", "e2", "major"),
        ]
    )
    parts = format_contradictions_for_synthesis(report).split("\n")
    assert parts[0] == "## Notable Contradictions in the Literature"
    assert parts[1] == ""  # v4 join puts a blank line under the (newline-ending) header
    assert parts[2].startswith("1. **Opposing Conclusions**")
    assert parts[3].startswith("2. **Data Inconsistency** (major)")


# --- unified_diff ------------------------------------------------------------

def test_unified_diff_exact_hunks():
    assert unified_diff("alpha\nbeta\ngamma\n", "alpha\ndelta\ngamma\n") == (
        "--- before\n"
        "+++ after\n"
        "@@ -1,3 +1,3 @@\n"
        " alpha\n"
        "-beta\n"
        "+delta\n"
        " gamma\n"
    )


def test_unified_diff_identical_inputs_and_custom_names():
    assert unified_diff("a\nb\n", "a\nb\n") == ""
    out = unified_diff("a\nb\n", "a\nc\n", old_name="old.txt", new_name="new.txt")
    assert out.startswith("--- old.txt\n+++ new.txt\n")
    assert "-b\n" in out
    assert "+c\n" in out


# --- colored_diff ------------------------------------------------------------

def test_colored_diff_exact_ansi_rendering():
    expected = (
        ESC
        + "[1m--- \x1b[0m\n"
        + ESC
        + "[1m+++ \x1b[0m\n"
        + ESC
        + "[36m@@ -1,3 +1,3 @@\x1b[0m\n"
        + " alpha\n"
        + ESC
        + "[31m-beta\x1b[0m\n"
        + ESC
        + "[32m+delta\x1b[0m\n"
        + " gamma"
    )
    assert colored_diff("alpha\nbeta\ngamma\n", "alpha\ndelta\ngamma\n") == expected


def test_colored_diff_identical_inputs_empty_and_context_uncolored():
    assert colored_diff("a\nb\n", "a\nb\n") == ""
    out = colored_diff("x\ny\n", "x\nz\n")
    assert "\n x\n" in out  # context line stays plain
    assert ESC + "[31m" in out  # red removal
    assert ESC + "[32m" in out  # green addition


# --- diff_stats --------------------------------------------------------------

def test_diff_stats_identical_replace_and_append():
    assert diff_stats("a\nb\nc\n", "a\nb\nc\n") == {"added": 0, "removed": 0, "unchanged": 3}
    assert diff_stats("a\nb\nc\n", "a\nx\nc\n") == {"added": 1, "removed": 1, "unchanged": 2}
    assert diff_stats("a\n", "a\nb\n") == {"added": 1, "removed": 0, "unchanged": 1}


# --- html_diff ---------------------------------------------------------------

def test_html_diff_builds_table_with_both_sides():
    out = html_diff("alpha\nbeta\ngamma\n", "alpha\ndelta\ngamma\n")
    assert "<table" in out
    assert "Before" in out
    assert "After" in out
    assert "delta" in out  # new text visible
    assert "diff_add" in out
    assert "diff_sub" in out


def test_html_diff_identical_inputs_still_produce_table():
    out = html_diff("a\nb\n", "a\nb\n")
    assert "<table" in out
    assert "a" in out
