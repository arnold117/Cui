"""Pure salient-term extraction for lexical candidate prefiltering.

``topic_terms`` reduces a claim body to a deterministic set of lowercase
content tokens, dropping a small English + generic-academic stopword set and
very short tokens. Deliberately simple and dependency-free (spec §7 词面粗筛:
"提取主题词做 overlap shortlist；纯函数、可测"). No stemming, no embeddings —
the prefilter only needs a cheap shared-vocabulary signal; the LLM judge does
the real contradiction reasoning.
"""

from __future__ import annotations

import re

# Minimal English function-word + generic-academic stopword set. Kept small and
# deterministic on purpose: aggressive filtering would risk dropping the very
# terms that distinguish two claims. Generic research-prose words ("study",
# "result", "method"...) are included because they co-occur across nearly every
# claim and so carry no discriminative signal for overlap ranking.
_STOPWORDS: frozenset[str] = frozenset(
    {
        # articles / determiners / conjunctions / prepositions
        "the", "a", "an", "and", "or", "but", "if", "then", "else", "of",
        "to", "in", "on", "at", "by", "for", "with", "as", "from", "into",
        "than", "that", "this", "these", "those", "it", "its", "is", "are",
        "was", "were", "be", "been", "being", "has", "have", "had", "do",
        "does", "did", "not", "no", "nor", "so", "such", "via", "per",
        "we", "our", "they", "their", "i", "you", "he", "she", "his", "her",
        "can", "may", "might", "will", "would", "should", "could", "more",
        "most", "less", "least", "very", "much", "many", "any", "all", "some",
        "between", "among", "over", "under", "about", "which", "while", "when",
        "where", "what", "who", "whom", "how", "because", "due",
        # generic research-prose words (co-occur everywhere → no signal)
        "study", "studies", "result", "results", "method", "methods",
        "approach", "approaches", "paper", "claim", "claims", "finding",
        "findings", "data", "show", "shows", "shown", "using", "used", "use",
        "based", "propose", "proposed", "proposes", "model", "models",
    }
)

# Tokens shorter than this are dropped (drops "a", "of"-style noise the
# stopword set may miss, plus stray single letters).
_MIN_TOKEN_LEN = 3

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def topic_terms(text: str) -> set[str]:
    """Extract salient lowercase content terms from ``text``.

    Lowercases, splits on non-alphanumeric boundaries, then drops stopwords
    and tokens shorter than ``_MIN_TOKEN_LEN``. Purely lexical and fully
    deterministic — identical input always yields the identical set.
    """
    if not text:
        return set()
    tokens = _TOKEN_RE.findall(text.lower())
    return {
        tok
        for tok in tokens
        if len(tok) >= _MIN_TOKEN_LEN and tok not in _STOPWORDS
    }
