"""v4 contradictions cherry-pick: pair-wise contradiction pure logic (T6 item 5).

来源: LitScribe v4 ``litscribe/tools/contradictions.py`` @ ``027583c``
(capability introduced in ``7e028cf`` "claim-level contradictions"). Ported
semantics-verbatim — no behavior "improvements": archive 保真, Cui native is
free to rebuild on top of these shapes later (slice1).

Native-equivalent check: nothing in Cui detects pair-wise contradictions
today. ``cui.research_universe`` only turns an ALREADY CONFIRMED single
evidence contradiction into a deterministic challenge
(``deterministic-evidence-contradiction-v1``, NO LLM) — a different concept
(post-confirmation reaction, not detection), so this module is not redundant.

Ported (pure, stdlib-only — the whole v4 module's only non-stdlib deps were
``langchain_openai.ChatOpenAI`` and the v4 ``PaperAnalysis`` domain object,
both confined to the LLM functions below that were NOT ported):
- ``Contradiction`` — v4 report-item shape (dataclass, verbatim).
- ``ContradictionReport`` — v4 report accumulator + ``count`` (verbatim).
- ``extract_cited_claims`` — the pure claim-citation extraction at the head
  of v4 ``detect_claim_contradictions`` (regex + ``max_claims`` cap), lifted
  to a standalone function so the v4 review-text parsing semantics survive
  without the LLM driver. slice1 can call this directly to parse v4-style
  review text.
- ``format_contradictions_for_synthesis`` — pure markdown rendering of a
  report (verbatim, incl. the optional paper-id → citation-key map).

NOT ported (and why; slice1 needing the full versions takes them back from v4
``LitScribe/litscribe/tools/contradictions.py``):
- ``CONTRADICTION_PROMPT`` — model-facing prompt text + JSON output contract,
  not logic. A native pair detector must write its own prompt for Cui's own
  LLM client (zero langchain), per native prompt conventions (the pre-RU
  ``build_contradiction_prompt`` precedent, docs/archive/pre-research-universe/
  spec-lens-contradiction.md).
- ``detect_claim_contradictions`` — async; calls ``model.ainvoke``, parses
  model JSON into ``Contradiction`` rows, and couples to v4 review-text claim
  numbering (``claim_a_num``/``claim_b_num``). Its pure head is ported above.
- ``_check_pair`` — async LLM call shaped around the v4 ``PaperAnalysis``
  domain object (``key_findings``/``paper_id``); the only "pure" part is
  bullet-rendering findings, no standalone algorithm.
- ``detect_contradictions`` — async orchestration (``asyncio.gather`` +
  ``Semaphore(3)``) over ``_check_pair``; its pair selection is a one-line
  ``itertools.combinations`` cap, not a reusable algorithm.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Contradiction:
    """One detected contradiction between two papers (v4 shape, verbatim).

    ``paper_a_id``/``paper_b_id`` are opaque ids — paper ids in v4's paper-pair
    flow, ``[@key]`` citation keys in the claim-level flow.
    """

    paper_a_id: str
    paper_b_id: str
    claim_a: str
    claim_b: str
    contradiction_type: str  # "methodological", "data_inconsistency", "opposing_conclusions"
    explanation: str
    severity: str  # "minor", "moderate", "major"


@dataclass
class ContradictionReport:
    """Accumulator for one contradiction-detection run (v4 shape, verbatim)."""

    total_pairs_checked: int = 0
    contradictions: list[Contradiction] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.contradictions)


def extract_cited_claims(
    review_text: str,
    max_claims: int = 15,
) -> list[tuple[str, str]]:
    """Extract claim citations of the form ``<text>[@key]`` from review text.

    Verbatim lift of the parsing head of v4 ``detect_claim_contradictions``
    (``re.findall(r"([^.!?\\n]{20,200})\\[@(\\w+)\\]", review_text)[:max_claims]``).
    Kept semantics-verbatim, warts included:

    - a claim is the 20–200 non-``.!?``/newline characters immediately before
      a ``[@\\w+]`` marker — i.e. normally the tail of the sentence that
      carries the citation, with sentence punctuation acting as the separator;
    - runs longer than 200 characters are greedily truncated to their trailing
      200 characters (mid-word cuts possible);
    - the matched claim text is NOT stripped (v4 stripped only when
      enumerating for the prompt) — the trailing space before ``[@`` survives;
    - markers with non-word keys (e.g. ``[@k-2]``) or preceded by fewer than
      20 characters do not match.

    ``max_claims`` caps the result to the first N matches, like v4. (v4 treated
    "fewer than two claims" as "nothing to compare" — that is detection-flow
    policy, not extraction semantics, so it lives with the unported driver.)
    """

    claims = re.findall(r"([^.!?\n]{20,200})\[@(\w+)\]", review_text)
    return claims[:max_claims]


def format_contradictions_for_synthesis(
    report: ContradictionReport,
    key_map: dict[str, str] | None = None,
) -> str:
    """Render a report as a markdown section for synthesis docs (verbatim).

    Empty report -> ``""``. ``key_map`` maps paper ids to ``[@key]`` citation
    keys for display; without it raw paper ids are shown.
    """

    if not report.contradictions:
        return ""

    lines = ["## Notable Contradictions in the Literature\n"]
    for i, c in enumerate(report.contradictions, 1):
        key_a = key_map.get(c.paper_a_id, c.paper_a_id) if key_map else c.paper_a_id
        key_b = key_map.get(c.paper_b_id, c.paper_b_id) if key_map else c.paper_b_id

        lines.append(
            f"{i}. **{c.contradiction_type.replace('_', ' ').title()}** "
            f"({c.severity}): [@{key_a}] reports: \"{c.claim_a}\", "
            f"while [@{key_b}] finds: \"{c.claim_b}\". "
            f"{c.explanation}"
        )

    return "\n".join(lines)
