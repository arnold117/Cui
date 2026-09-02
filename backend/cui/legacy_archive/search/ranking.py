"""CJK-aware English term extraction + IDF-weighted keyword ranking.

Pure, deterministic, stdlib-only. Ported from LitScribe commit 027583c
("fix(search): CJK query routing + IDF-weighted prefilter + LLM selection as
primary gate", ``litscribe/tools/pipeline.py`` + ``tools/search.py``),
restricted to the pure functions — no LLM, no search sources, no network:

- ``extract_core_terms`` mirrors the English core-term extraction of v4's
  ``step_search``: lowercase whitespace tokens, length >= 4, stopword
  filter, and whole-token exclusion of anything containing a CJK character
  (a Chinese whole-phrase must never substring-match English abstracts).
- ``rank_by_idf`` mirrors v4's weighted relevance ordering: each term's
  weight is ``log(1 + n / df)`` (df = number of texts containing the term,
  floor 1), each text's score is the sum of the weights of the terms it
  hits, score > 0 texts come first in descending score, and zero-score texts
  trail in their original relative order (v4 semantics: the matched pool is
  kept; raw order is the fallback). Ranking only, no truncation — callers
  decide how many texts to keep.

This is the pure-function contract for the slice1 corpus-retrieval takeover
(docs/plan-v5-slice0.md, T6 item 1; source commit 027583c): callers decide
which queries to feed (v4 used only its first three unique queries) and
where to slice the ranked pool.
"""

from __future__ import annotations

import math

# Verbatim copy of the inline _STOP set from LitScribe 027583c
# (litscribe/tools/pipeline.py) so the default table cannot drift.
_DEFAULT_STOPWORDS = frozenset(
    {
        "with",
        "from",
        "that",
        "this",
        "have",
        "been",
        "their",
        "using",
        "based",
        "study",
        "analysis",
        "approach",
        "method",
        "novel",
        "recent",
        "review",
        "paper",
        "results",
    }
)

# v4 excluded the single ideograph range U+4E00-U+9FFF ("一" <= c <= "鿿").
# Relaxed to U+3000-U+9FFF so CJK punctuation / fullwidth forms from the
# U+3000 block are excluded too; pure-ASCII queries are unaffected.
_CJK_MIN = "\u3000"
_CJK_MAX = "\u9fff"

__all__ = ["extract_core_terms", "rank_by_idf"]


def _contains_cjk(word: str) -> bool:
    return any(_CJK_MIN <= c <= _CJK_MAX for c in word)


def extract_core_terms(
    queries: list[str], stopwords: frozenset[str] | None = None
) -> list[str]:
    """English core terms from queries: len >= 4, not stopwords, no CJK.

    ``queries`` are lowercased and whitespace-split. A token containing any
    CJK character (U+3000-U+9FFF; v4 used U+4E00-U+9FFF) is dropped whole —
    Chinese phrases must never act as substring keywords against
    English-only titles/abstracts. Terms keep first-appearance order and are
    deduplicated (v4 held a ``set``). ``stopwords=None`` selects the default
    table (identical to v4's inline ``_STOP``); a caller-supplied table
    replaces it entirely.
    """
    stop = _DEFAULT_STOPWORDS if stopwords is None else stopwords
    terms: list[str] = []
    seen: set[str] = set()
    for query in queries:
        for word in query.lower().split():
            if (
                len(word) >= 4
                and word not in stop
                and word not in seen
                and not _contains_cjk(word)
            ):
                seen.add(word)
                terms.append(word)
    return terms


def rank_by_idf(
    texts: list[tuple[str, str | None]], terms: list[str]
) -> list[int]:
    """Rank (title, abstract) texts by IDF-weighted term hits; return indices.

    A text "hits" a term when the term is a substring of the lowercased
    ``"<title> <abstract>"`` — v4 semantics: one hit per term per text, so a
    term appearing in both title and abstract still scores once. With
    ``df`` = number of texts containing the term (floor 1) and ``n`` =
    len(texts) (floor 1), each term weighs ``log(1 + n / df)`` and a text's
    score is the sum of the weights of the terms it hits: rare terms dominate
    common ones, so a paper matching only ubiquitous words (power/time/model)
    can no longer outrank the text that actually carries the rare topic term.

    Returns the sorted text indices — every text, no truncation: score > 0
    texts first in descending score (ties keep input order), then zero-score
    texts in their original relative order: v4's "keep the matched pool,
    raw order as fallback" semantics.
    """
    n = len(texts) or 1
    haystacks = [
        f"{title or ''} {abstract or ''}".lower() for title, abstract in texts
    ]
    df = {
        term: (sum(1 for text in haystacks if term in text) or 1)
        for term in terms
    }
    weights = {term: math.log(1.0 + n / df[term]) for term in terms}

    scores = [
        sum(weights[term] for term in terms if term in text)
        for text in haystacks
    ]
    matched = [(i, score) for i, score in enumerate(scores) if score > 0.0]
    matched.sort(key=lambda pair: pair[1], reverse=True)
    return [i for i, _ in matched] + [
        i for i, score in enumerate(scores) if score == 0.0
    ]
