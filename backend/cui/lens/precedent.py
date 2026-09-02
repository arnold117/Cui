"""Kill-precedent selection for the mainline grill (判例先验 / precedent prior).

The mainline ``auto_challenge`` eats the researcher's OWN past KILL 判例 so the
question attacks where their ideas have actually died before (spec
``docs/spec-precedent-prior.md`` §2). This module is the SELECTION half —
pure, deterministic, zero I/O, fully unit-testable; the gathering half (which
needs the Library's claims + event streams) lives in ``GrillService``.

Two rules are enforced here, both structural rather than prompt-level:

- **只吃 kill 判例** (Q4): survive precedents are dropped. Feeding them in
  would be 前功赦免 — "he withstood one of these before" can only ever SOFTEN
  the questioning, and it collides head-on with survived ≠ 正确性证书.
- **确定性预算** (Q3): ts 倒序最近 ``PRECEDENT_BUDGET`` 条 — a deterministic,
  assertable cap, NOT a relevance filter. Deliberately NOT ``prefilter_candidates``:
  topic-word overlap would keep only same-topic precedents (already handled by
  ②跨想法矛盾检测) and throw away exactly the valuable ones — the methodological
  habit that repeats across unrelated subjects, where lexical overlap is zero.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, NamedTuple

from cui.llm.prompts import ClaimPrecedent

# Deterministic injection budget (spec §2 Q3). Exceeding it is the structural
# trigger for revisiting selection/compression (判例蒸馏), not a headcount.
PRECEDENT_BUDGET = 12


class DatedPrecedent(NamedTuple):
    """A ``ClaimPrecedent`` plus the ts of the ruling verdict that set it.

    ``ts`` is carried alongside rather than inside ``ClaimPrecedent`` because
    it is selection input, never prompt content — the model is shown the
    verdict, not its clock.
    """

    ts: datetime
    precedent: ClaimPrecedent


def select_kill_precedents(
    candidates: Iterable[DatedPrecedent],
    budget: int = PRECEDENT_BUDGET,
) -> list[ClaimPrecedent]:
    """The kill precedents to inject: most recent ``budget``, newest first.

    - Non-kill precedents are dropped (``outcome != "killed"``) — survive never
      reaches the prompt.
    - Ordered by ts descending; ties broken by claim id descending, so the
      result is stable no matter what order the Library enumerated in.
    - At most ``budget`` are returned. An empty input yields ``[]``, and the
      caller then keeps today's prompt verbatim (冷启动不沉默、不空转).
    """
    kills = [d for d in candidates if d.precedent.outcome == "killed"]
    kills.sort(key=lambda d: (d.ts, d.precedent.claim_id), reverse=True)
    return [d.precedent for d in kills[:budget]]
