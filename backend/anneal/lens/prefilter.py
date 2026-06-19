"""Pure lexical prefilter for contradiction candidates.

Ranks past claims by topic-term overlap with the current claim body and returns
the top-K shortlist. This is the cheap "词面/主题词粗筛" gate (spec §4 Q-B,
§7): only the shortlist is handed to the LLM judge, so the per-grill LLM cost
stays bounded on a solo-scale library. Candidates that share no topic term with
the current claim are dropped (zero overlap = no lexical signal at all).

Pure: no I/O, deterministic ranking, fully unit-testable.
"""

from __future__ import annotations

from anneal.domain.models import Claim
from anneal.lens.topic_terms import topic_terms


def _overlap_count(current_terms: set[str], candidate_body: str) -> int:
    """Shared topic-term count between the current claim and a candidate body."""
    return len(current_terms & topic_terms(candidate_body))


def prefilter_candidates(
    current_body: str,
    candidates: list[Claim],
    top_k: int = 8,
) -> list[Claim]:
    """Rank ``candidates`` by topic-term overlap with ``current_body``; return top-K.

    - Overlap = number of shared topic terms (see ``topic_terms``).
    - Candidates with ZERO overlap are dropped entirely.
    - Higher overlap ranks first; ties are broken deterministically by claim id
      (ascending), so the result is stable regardless of input order.
    - At most ``top_k`` claims are returned.
    """
    current_terms = topic_terms(current_body)
    if not current_terms:
        return []

    scored: list[tuple[int, Claim]] = []
    for cand in candidates:
        overlap = _overlap_count(current_terms, cand.body)
        if overlap > 0:
            scored.append((overlap, cand))

    # Sort by overlap desc, then claim id asc — fully deterministic.
    scored.sort(key=lambda pair: (-pair[0], pair[1].id))
    return [claim for _, claim in scored[:top_k]]
