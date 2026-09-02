"""Unit tests for the ported v4 CJK + IDF ranking pure logic.

Covers ``cui.legacy_archive.search.ranking`` (source: LitScribe commit
027583c, "CJK query routing + IDF-weighted keyword prefilter", pure part;
port scope: docs/plan-v5-slice0.md T6 item 1). All tests are offline and
deterministic — no LLM, search sources, or network involved.
"""
from cui.legacy_archive.search.ranking import extract_core_terms, rank_by_idf


# --- (a) CJK exclusion ----------------------------------------------------


def test_extract_core_terms_excludes_chinese_whole_words():
    # Chinese whole-phrases never become core terms; English words survive.
    assert extract_core_terms(
        ["道德推脱与施害者心理 disengagement mechanisms"]
    ) == ["disengagement", "mechanisms"]


def test_extract_core_terms_pure_cjk_query_yields_nothing():
    assert extract_core_terms(["道德推脱如何随时间演变"]) == []


def test_extract_core_terms_mixed_latin_cjk_token_dropped_whole():
    # v4 semantics: one token containing any CJK char is dropped entirely.
    assert extract_core_terms(["deeplearning深度学习模型 survey"]) == ["survey"]
    # CJK punctuation (U+3002, inside the relaxed U+3000-U+9FFF range) also
    # disqualifies a token.
    assert extract_core_terms(["moral-disengagement。"]) == []


def test_extract_core_terms_case_length_and_default_stopwords():
    assert extract_core_terms(["Power and Time with this study method"]) == [
        "power",
        "time",
    ]
    assert extract_core_terms(["cat dogfish"]) == ["dogfish"]  # len < 4 gone


def test_extract_core_terms_custom_stopwords_replace_default():
    assert extract_core_terms(["alpha beta gamma"], stopwords=frozenset({"alpha"})) == [
        "beta",
        "gamma",
    ]
    # Caller table replaces the default: default-stopped words now survive.
    assert extract_core_terms(
        ["analysis findings"], stopwords=frozenset()
    ) == ["analysis", "findings"]


def test_extract_core_terms_dedupes_preserving_first_appearance_order():
    assert extract_core_terms(["alpha beta", "BETA gamma", "gamma"]) == [
        "alpha",
        "beta",
        "gamma",
    ]


def test_extract_then_rank_shape_of_a_real_query_set():
    # End-to-end shape: "and" / "in" dropped by the length filter,
    # CJK query contributes nothing, first-appearance order preserved.
    terms = extract_core_terms(
        [
            "time and model design tradeoffs",
            "moral disengagement in offenders",
            "道德推脱 时间序列",
        ]
    )
    assert terms == [
        "time",
        "model",
        "design",
        "tradeoffs",
        "moral",
        "disengagement",
        "offenders",
    ]


# --- (b) IDF: common words do not outrank the rare-term text ---------------


def test_rank_by_idf_rare_term_text_beats_common_word_only_text():
    """'Power and Time in Model Design' matches only ubiquitous terms.

    All five texts contain ``time`` and ``model`` (df = 5 each -> weight
    log(1 + 5/5) = log 2 ≈ 0.693), so the common-word-only paper scores
    2 * log 2 ≈ 1.386. ``disengagement`` appears in one text only (df = 1 ->
    log(1 + 5/1) = log 6 ≈ 1.792); that text alone already beats two full
    common-word hits, and its total (≈ 3.178) ranks it first.
    """
    texts = [
        (
            "Power and Time in Model Design",
            "Balancing power, time and model scale across training schedules.",
        ),
        (
            "Energy and Time Budgets for Model Families",
            "Time measurements against model size trade-offs.",
        ),
        (
            "Real-Time Inference for Streaming Models",
            "Live time constraints for small models.",
        ),
        (
            "A Survey of Time Series Model Benchmarks",
            "Comparing time-series and tabular models.",
        ),
        (
            "Moral Disengagement in Corporate Offenders",
            "How disengagement evolves over time in a model of offender psychology.",
        ),
    ]
    ranked = rank_by_idf(texts, ["time", "model", "disengagement"])
    # On-topic text (rare term) first; all common-word-only texts trail, in
    # their original relative order (equal scores tie stably).
    assert ranked == [4, 0, 1, 2, 3]


# --- (c) monotone weights: double occurrence + df sensitivity --------------


def test_rank_by_idf_weights_are_monotone_in_rareness():
    """The unique rare-term carrier ranks first; widening its df weakens it.

    Corpus A: ``disengagement`` appears in exactly one text — twice (title
    AND abstract; v4 scores a term once per text, so the double occurrence
    is not a second score, it just makes document-level containment certain).
    df = 1 -> weight log(1 + 5) ≈ 1.792 > log 2 ≈ 0.693 (the ``time`` hit
    shared by every text), so the carrier ranks first.

    Corpus B: the same term also appears in a second text -> df = 2, weight
    drops to log(1 + 5/2) ≈ 1.253; both carriers now tie at the top in input
    order, and the lone-carrier's first place is gone — weight is monotone
    decreasing in df.
    """
    terms = ["time", "disengagement"]
    texts_a = [
        ("Power and Time in Model Design", "Time budgets shape architecture choices."),
        (
            "Moral Neutralisation in Offenders",
            "Neutralising guilt needs time to emerge.",
        ),
        ("Time Series Benchmarks", "Measuring time-dependent accuracy."),
        ("Time Management in Teams", "Allocating time across projects."),
        (
            "The Ethics of Disengagement",
            "Disengagement is a time-bounded coping strategy.",
        ),
    ]
    assert rank_by_idf(texts_a, terms) == [4, 0, 1, 2, 3]

    texts_b = [
        texts_a[0],
        (
            "Moral Neutralisation in Offenders",
            "Neutralising guilt needs time to emerge through disengagement.",
        ),
        texts_a[2],
        texts_a[3],
        texts_a[4],
    ]
    ranked_b = rank_by_idf(texts_b, terms)
    assert ranked_b == [1, 4, 0, 2, 3]  # df = 2: carriers tie, then the rest


# --- (d) zero-hit texts stay at the tail, original relative order -----------


def test_rank_by_idf_zero_hit_texts_trail_in_original_order():
    """Everything is ranked, nothing dropped: matched texts first (positive
    score, descending), zero-score texts after them in input order."""
    texts = [
        (
            "Moral Disengagement in Offenders",
            "How disengagement unfolds over time.",
        ),  # 0: rare + common
        ("Time Series Benchmarks", "Time-dependent accuracy measures."),  # 1: common
        ("Microbes in Extreme Environments", "Bacterial survival under pressure."),  # 2: none
        ("Zero-Shot Learning Notes", "Latent space geometry."),  # 3: none
        ("Power Grid Resilience", "Power flow control."),  # 4: none
    ]
    ranked = rank_by_idf(texts, ["time", "model", "disengagement"])
    assert ranked[0] == 0  # rare-term hit on top
    assert ranked[-3:] == [2, 3, 4]  # zeros kept, input order preserved
    assert set(ranked) == {0, 1, 2, 3, 4}  # no truncation


def test_rank_by_idf_no_terms_and_empty_inputs():
    assert rank_by_idf([], []) == []
    assert rank_by_idf([("nothing here", None)], []) == [0]  # zero score, kept
    assert rank_by_idf(
        [("Moral Disengagement", None), ("", "no match here")], ["disengagement"]
    ) == [0, 1]


# --- (e) determinism -------------------------------------------------------


def test_rank_by_idf_deterministic_across_calls():
    queries = ["moral disengagement in offenders", "道德推脱 mechanisms"]
    texts = [
        ("Moral Disengagement in Offenders", "How disengagement unfolds over time."),
        ("Time Series Benchmarks", "Time-dependent accuracy measures."),
        ("Power Grid Resilience", "Power flow control."),
        ("Microbes in Extreme Environments", "Bacterial survival under pressure."),
    ]
    terms = extract_core_terms(queries)
    first = rank_by_idf(texts, terms)
    assert first == rank_by_idf(texts, terms) == [0, 1, 2, 3]
    assert extract_core_terms(queries) == extract_core_terms(queries)
