from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from anneal.domain.events import Event

# Deterministic rationale budget for precedent injection (spec Q4: 单条
# rationale 截前 300 字加省略号 — no LLM summarization, no extra hop).
RATIONALE_TRUNCATE_CHARS = 300

# Output-language rule appended to the tail of every system prompt whose
# output carries user-visible natural language (question / tension / rationale
# / reasoning / evidence / assessment / revival_condition / reason). Without
# it the model drifts to English on a Chinese claim — one board, two
# languages. Structured fields (enums, ids, JSON keys) are unaffected: the
# rule speaks only to natural-language fields.
OUTPUT_LANGUAGE_INSTRUCTION = (
    "Write all natural-language output fields in the same language as the "
    "CURRENT claim."
)


def truncate_rationale(rationale: str, limit: int = RATIONALE_TRUNCATE_CHARS) -> str:
    """Deterministically cap a verdict rationale for prompt injection.

    Pure function: first ``limit`` characters plus an ellipsis when longer,
    verbatim otherwise. 确定性优先 — never an LLM summary.
    """
    if len(rationale) <= limit:
        return rationale
    return rationale[:limit] + "…"


class ClaimPrecedent(NamedTuple):
    """A grilled past claim + the 判例四元组 its ruling verdict left behind.

    ``outcome`` uses claim_status vocabulary ("survived"/"killed").
    ``death_cause`` is None for survived claims AND for legacy kills recorded
    before death-cause triage (rendered as "unclassified" — 死因未分类).
    """

    body: str
    outcome: str
    claim_id: str
    death_cause: str | None = None
    rationale: str = ""
    revival_condition: str | None = None


# One-line gloss per death cause, teaching the model what each kill MEANS
# (the discriminating value: different deaths are entirely different anchors).
_DEATH_CAUSE_GLOSS = {
    "refuted": (
        "refuted — factually wrong (truth-axis kill; includes duplicates of "
        "already-killed ideas)"
    ),
    "not_worth": (
        "not_worth — correct but judged NOT WORTH doing (worth-axis / taste kill)"
    ),
    "boundary": (
        "boundary — the original formulation died but drew a boundary; a "
        "narrowed successor claim lives on"
    ),
    "circumstantial": (
        "circumstantial — not conclusively dead (could not be defended right "
        "then); has a revival condition"
    ),
}


def format_precedent_lines(
    outcome: str,
    death_cause: str | None,
    rationale: str,
    revival_condition: str | None,
) -> list[str]:
    """Render the 判例四元组 as bare prompt lines (callers indent/bullet).

    - Death cause line for killed claims only; legacy kills (no recorded
      cause) are marked "unclassified" — never pretend a cause exists.
    - Rationale line when non-empty, deterministically truncated.
    - Revival condition line only for circumstantial kills (spec Q4: 仅偶然死).
    Empty output means there is no precedent to inject (e.g. a legacy survive
    with an empty rationale) and callers keep their legacy prompt verbatim.
    """
    lines: list[str] = []
    if outcome == "killed":
        gloss = _DEATH_CAUSE_GLOSS.get(death_cause or "")
        if gloss:
            lines.append(f"Death cause: {gloss}")
        else:
            lines.append(
                "Death cause: unclassified (legacy verdict — recorded before "
                "death-cause triage)"
            )
    if rationale:
        lines.append(f"Verdict rationale: {truncate_rationale(rationale)}")
    if death_cause == "circumstantial" and revival_condition:
        lines.append(f"Revival condition: {revival_condition}")
    return lines


# Prompt labels per ground stance. silent has NO label on purpose — 查无
# evidence bears nothing on the claim and never enters the block.
_STANCE_LABELS = {
    "supports": "SUPPORTS",
    "contradicts": "CONTRADICTS",
    # Legacy 未分态: the paper did not support the claim, but whether it was
    # silent or contradicting was never recorded — labeled honestly, never
    # upgraded to CONTRADICTS.
    "not_supported": "NOT_SUPPORTED",
}


def format_evidence_block(evidence_events: list[Event]) -> str:
    """Render confirmed GROUND events into a compact, LLM-readable block.

    One item per line:
      ``- [SUPPORTS] {source}:{title} — {evidence} ({assessment})``
    with the label resolved from the payload's three-state ``verdict``
    (``ground_stance``): supports → ``[SUPPORTS]``, contradicts →
    ``[CONTRADICTS]`` (explicitly counter-evidence), legacy ``supported:
    False`` → ``[NOT_SUPPORTED]`` (未分态 — never guessed into contradicts).
    ``silent`` grounds are SKIPPED — 查无 bears nothing on the claim, so it
    never enters the evidence block. Empty evidence/assessment segments are
    omitted gracefully. An empty input list yields "" (callers treat "" as
    "no evidence" and keep the legacy prompt verbatim).
    """
    from anneal.domain.projections import ground_stance

    lines: list[str] = []
    for e in evidence_events:
        p = e.payload
        stance = _STANCE_LABELS.get(ground_stance(p) or "")
        if stance is None:
            continue  # silent (查无) or malformed — nothing to weigh
        source = p.get("source", "")
        title = p.get("title", "")
        head = ":".join(part for part in (source, title) if part) or "(untitled)"
        line = f"- [{stance}] {head}"
        evidence = p.get("evidence", "")
        if evidence:
            line += f" — {evidence}"
        assessment = p.get("assessment", "")
        if assessment:
            line += f" ({assessment})"
        lines.append(line)
    return "\n".join(lines)


def build_challenge_prompt(claim: str, context: str, evidence: str = "") -> tuple[str, str]:
    system = (
        "You are a rigorous academic reviewer. Your job is to generate a single, "
        "focused challenge question that tests the validity of a research claim. "
        "The question should target the weakest aspect of the claim — methodology, "
        "evidence, logical reasoning, or scope of generalization.\n\n"
        "Respond ONLY with valid JSON in this exact format:\n"
        '{"question": "<your challenging question>", '
        '"target_aspect": "<methodology|evidence|logic|scope>"}'
    )
    user = f"Claim: {claim}\n\nContext: {context}\n\nGenerate one focused challenge question for this claim."
    if evidence:
        system += (
            "\n\nGround your challenge in the provided literature evidence where "
            "relevant: use CONTRADICTS papers to attack the claim directly, and "
            "for SUPPORTS papers, probe whether their scope and methodology "
            "actually cover the claim's generalization. NOT_SUPPORTED entries "
            "are legacy judgments recorded before three-state grounding: the "
            "paper did not support the claim, but whether it was silent or "
            "contradicting was never recorded — do NOT treat them as "
            "refutations."
        )
        user = (
            f"Claim: {claim}\n\nContext: {context}\n\n"
            f"Literature evidence:\n{evidence}\n\n"
            "Generate one focused challenge question for this claim."
        )
    system += "\n\n" + OUTPUT_LANGUAGE_INSTRUCTION
    return system, user


def build_grounding_prompt(claim: str, paper_title: str, paper_abstract: str) -> tuple[str, str]:
    """Three-state grounding judgment (supports / contradicts / silent).

    A binary supported-or-not collapses two entirely different states: "the
    literature does not discuss this claim" and "the literature strikes this
    claim". The verdict is a three-way enum with a SKEPTICAL default:
    contradicts requires the abstract to GENUINELY bear on the claim — the
    model must never slide from "does not support" into "contradicts"; when
    unsure whether the abstract bears on the claim at all, the verdict is
    silent. silent is a legitimate first-class finding (查无), not a failure.
    """
    system = (
        "You are a rigorous evidence assessor. Your job is to judge how a "
        "research paper bears on a given claim, based solely on the paper's "
        "title and abstract. Do not invent evidence not present in the "
        "abstract.\n\n"
        "Pick exactly one verdict:\n"
        '- "supports": the abstract positively supports the claim.\n'
        '- "contradicts": the abstract GENUINELY addresses the claim AND '
        "weakens or refutes it. This requires the abstract to actually bear "
        "on the claim — do NOT slide from \"does not support\" into "
        '"contradicts". Absence of support is NOT contradiction.\n'
        '- "silent": the abstract does not bear on the claim. This is a '
        "legitimate, first-class finding — reporting that the literature is "
        "silent is just as valuable as reporting support. Never stretch an "
        "unrelated abstract into a verdict.\n\n"
        "SKEPTICAL DEFAULT: if you are unsure whether the abstract bears on "
        'the claim at all, the verdict is "silent", never "contradicts".\n\n'
        "Respond ONLY with valid JSON in this exact format:\n"
        '{"verdict": "supports" | "contradicts" | "silent", '
        '"evidence": "<short quote or paraphrase from the abstract that bears on '
        'the claim, or empty string if none>", '
        '"assessment": "<one-sentence rationale>"}'
    )
    system += "\n\n" + OUTPUT_LANGUAGE_INSTRUCTION
    user = (
        f"Claim: {claim}\n\n"
        f"Paper title: {paper_title}\n\n"
        f"Paper abstract: {paper_abstract}\n\n"
        "Does this paper support the claim, contradict it, or is it silent "
        "on it?"
    )
    return system, user


def build_contradiction_prompt(
    current_claim: str,
    past_claim: str,
    past_outcome: str,
    past_death_cause: str | None = None,
    past_rationale: str = "",
    past_revival_condition: str | None = None,
) -> tuple[str, str]:
    """Judge whether the CURRENT claim conflicts with the user's OWN PAST claim.

    The past claim was already grilled by the user and either ``survived`` or
    ``killed`` (``past_outcome``). The reviewer identifies the *factual*
    relationship between the two claims and, if they conflict, poses a single
    challenge question grounded in that conflict.

    判例注入 (spec-verdict-precedent §2 Q4): the optional precedent fields
    carry the past verdict's death cause, rationale (deterministically
    truncated) and revival condition. When any of them yield content, a
    "Past verdict precedent" block is appended to the user prompt and the
    system prompt gains death-cause weighing guidance — its point is LOWERING
    false positives: a past claim killed on taste (not_worth) plus a similar
    current claim is NOT a hard contradiction. With no precedent content the
    legacy 3-arg prompt is returned verbatim.

    RED LINE (spec §2): the reviewer must NOT score idea quality or give taste
    judgments — only identify the relationship and pose a question. The verdict
    on the current claim stays with the user (取证不定见).
    """
    system = (
        "You are a rigorous reviewer comparing a researcher's CURRENT claim "
        "against one of their OWN PAST claims that they previously grilled and "
        "resolved (it either survived or was killed). Your ONLY job is to "
        "identify the factual relationship between the two claims and, if they "
        "conflict, to pose a single challenge question grounded in that "
        "conflict.\n\n"
        "Classify the relationship:\n"
        '- "hard": a logical contradiction — the current claim asserts X and '
        "the past claim asserts not-X (they cannot both hold).\n"
        '- "duplicate": the current claim is essentially the same claim the '
        "user already grilled (same assertion, restated).\n"
        '- "soft": mere incremental-pattern tension — no logical conflict, e.g. '
        "the current claim is yet another variant of the same method/angle as "
        "the past one. Use this ONLY when there is a real tension but NOT a "
        "logical contradiction or duplicate.\n\n"
        "CRITICAL — you must NOT score, rank, praise, or criticize the quality, "
        "novelty, or merit of either idea. Do NOT decide whether the current "
        "claim is good or should survive. State only the factual relationship "
        "and pose a question; the user decides the verdict.\n\n"
        'Set "contradicts" to true ONLY when the relationship is hard, '
        "duplicate, or a genuine soft tension worth surfacing; otherwise false.\n\n"
        "Respond ONLY with valid JSON in this exact format:\n"
        '{"contradicts": true or false, '
        '"tension_type": "hard" or "duplicate" or "soft", '
        '"tension": "<where they factually conflict, no quality judgment>", '
        '"question": "<the challenge question to pose to the user>"}'
    )
    precedent_lines = format_precedent_lines(
        past_outcome, past_death_cause, past_rationale, past_revival_condition
    )
    if precedent_lines:
        system += (
            "\n\nWEIGH THE PAST VERDICT'S DEATH CAUSE before calling a "
            "conflict — different deaths mean entirely different things:\n"
            "- not_worth (taste kill): the user judged the past claim CORRECT "
            "but not worth doing. Similarity of the current claim to it is "
            'NOT a logical contradiction — do NOT emit "hard" from mere '
            'similarity to a taste-killed claim; at most "duplicate" (same '
            'assertion restated) or "soft" (pattern tension).\n'
            "- circumstantial: the past claim was NOT conclusively wrong "
            "(shelved with a revival condition). Do NOT treat that kill as an "
            "established negative result contradicting the current claim.\n"
            "- refuted: the past claim WAS factually wrong — a current claim "
            "restating it duplicates an already-refuted idea; one asserting "
            "its negation AGREES with the record (no conflict).\n"
            "- boundary: only the over-broad original died; a narrowed "
            "successor lives on. Weigh the conflict against the boundary "
            "drawn, not the dead formulation alone.\n"
            "- unclassified (legacy): no recorded cause — weigh the verdict "
            "rationale text itself; do not guess a cause."
        )
        block = "\n".join(f"- {line}" for line in precedent_lines)
        user = (
            f"Current claim (being grilled now): {current_claim}\n\n"
            f"Past claim (the user already {past_outcome} this one): {past_claim}\n\n"
            f"Past verdict precedent:\n{block}\n\n"
            "Do these claims contradict, duplicate, or stand in tension? "
            "Weigh the death cause; identify the factual relationship and, "
            "if so, the challenge question."
        )
    else:
        user = (
            f"Current claim (being grilled now): {current_claim}\n\n"
            f"Past claim (the user already {past_outcome} this one): {past_claim}\n\n"
            "Do these claims contradict, duplicate, or stand in tension? "
            "Identify the factual relationship and, if so, the challenge question."
        )
    system += "\n\n" + OUTPUT_LANGUAGE_INSTRUCTION
    return system, user


def build_taste_prompt(
    claim: str,
    prior_art_papers: list[dict],
    past_claims: list[ClaimPrecedent],
) -> tuple[str, str]:
    """Position a CURRENT claim on the taste/worth axis (Lens 第二刀 / 品味锚).

    ``prior_art_papers``: neutral paper dicts (title/abstract/source_id) — the
    NOVELTY anchor. May be EMPTY (degraded: literature未对位).
    ``past_claims``: ``ClaimPrecedent`` tuples — the user's OWN grilled
    kill/survive record, the TASTE anchor, now carrying each ruling verdict's
    判例四元组 (outcome + death cause + truncated rationale + revival
    condition). Guaranteed NON-empty (history is the gate; the service won't
    call this without history). A not_worth kill is the STRONGEST
    revealed-taste signal and the system prompt says so explicitly; legacy
    kills without a recorded cause render as "unclassified".

    Implements the four anti-sycophancy layers (spec §2 Q-C, the make-or-break):
    no-anchor-no-verdict, anchor-first, skeptical asymmetric bar, anti-praise.

    RED LINE: taste = WORTH relative to the USER'S OWN history, NEVER the
    field's consensus; literature only establishes novelty; NEVER an absolute
    quality score or "good/bad" — only RELATIVE positioning.
    """
    system = (
        "You position a researcher's CURRENT claim on the TASTE/WORTH axis, "
        "anchored to two kinds of fact: (1) real prior-art papers, and (2) the "
        "researcher's OWN past claims that they already grilled (survived or "
        "killed).\n\n"
        "TWO ORTHOGONAL AXES — do NOT conflate them:\n"
        "- NOVELTY axis: has this been done / how much increment? This is "
        "literature-measurable and FACTUAL. The prior-art papers establish "
        "novelty ONLY.\n"
        "- TASTE/WORTH axis: is this WORTH doing? This is a PERSONAL, often "
        "CONTRARIAN judgment. It is NEVER derivable from consensus or from what "
        "everyone in the field does. The ONLY legitimate source of the taste "
        "judgment is the researcher's OWN past claims — what they killed, what "
        "they defended, what they keep choosing to do or not do. NEVER anchor "
        "taste to 'what the field considers good' or 'what is on-trend'.\n\n"
        "ANTI-SYCOPHANCY — THIS IS THE FAILURE MODE. Your default behavior is to "
        "praise and agree with the claim. That default is WRONG here and "
        "corrodes trust. You must instead give an honest, often UNFLATTERING, "
        "RELATIVE positioning, and explicitly NAME what is NOT novel.\n\n"
        "Follow these rules:\n"
        "1. NO ANCHOR, NO VERDICT: only assign a tier you can ANCHOR to a "
        "SPECIFIC paper or past claim that was actually provided to you, cited "
        "by its exact title or id. If you cannot anchor the tier to a real "
        "provided paper or past claim, say so — emit empty anchors and the "
        "system will drop the verdict. NEVER invent a paper or claim.\n"
        "2. ANCHOR FIRST, THEN POSITION: FIRST identify the closest prior work "
        "(from the given papers) and the most-similar past claim(s) (from the "
        "given history). THEN let the tier FOLLOW from those anchors. The tier "
        "must be derived from the anchors, not from a global impression.\n"
        "3. SKEPTICAL, ASYMMETRIC BAR: default toward 'replication' or "
        "'incremental'. 'tasteful' requires an EXPLICIT argument for why this is "
        "NOT just incremental or replication, PLUS strong anchors. Do NOT hand "
        "out 'tasteful' easily.\n"
        "4. NEVER SCORE: do NOT output any absolute quality score, rating, or "
        "'good/bad' verdict. Only RELATIVE positioning — relative to these "
        "papers and relative to the user's own past claims.\n\n"
        "The four tiers:\n"
        "- 'replication': essentially already done (in the prior art or the "
        "user's history).\n"
        "- 'incremental': a small increment over existing work / the user's own "
        "pattern.\n"
        "- 'novel_but_tasteless': genuinely novel on the novelty axis, but the "
        "user's own history reveals it is not worth doing.\n"
        "- 'tasteful': novel AND worth doing, judged against the user's OWN "
        "revealed preferences — the highest bar, requires strong anchors.\n\n"
        "DEATH-CAUSE PRECEDENTS — read each past claim's verdict precedent "
        "(death cause + rationale) when provided:\n"
        "- A past claim killed as not_worth is the STRONGEST revealed-taste "
        "signal: the user explicitly judged that direction CORRECT but not "
        "worth doing. If the current claim resembles a not_worth-killed past "
        "claim, that history argues for 'novel_but_tasteless' (or "
        "'incremental') and you MUST name that precedent as the anchor.\n"
        "- A circumstantial kill is NOT a taste signal — the user shelved it "
        "without judging worth; do not read taste into it.\n"
        "- A boundary kill reveals taste FOR the narrowed successor "
        "direction, not against the whole area.\n"
        "- An unclassified death cause (legacy) means the kill predates "
        "triage — use the rationale text; do not guess a cause.\n\n"
        "Respond ONLY with valid JSON in this exact format:\n"
        '{"tier": "replication" | "incremental" | "novel_but_tasteless" | '
        '"tasteful", '
        '"reasoning": "<relative positioning, NO scoring, name what is not '
        'novel>", '
        '"anchored_papers": [{"title": "<exact title of a provided paper>"}], '
        '"anchored_claims": [{"past_claim_id": "<id of a provided past claim>"}], '
        '"question": "<a refutable challenge, e.g. what is the worthwhile '
        'increment here?>"}\n\n' + OUTPUT_LANGUAGE_INSTRUCTION
    )

    if prior_art_papers:
        papers_block = "\n\n".join(
            f"- Title: {p.get('title', '')}\n  Abstract: {p.get('abstract', '')}"
            for p in prior_art_papers
        )
    else:
        papers_block = (
            "(none — no prior-art papers matched; the novelty axis cannot be "
            "anchored to literature. Base your positioning on the user's history "
            "and note in reasoning that literature did not match.)"
        )

    past_items: list[str] = []
    for pc in past_claims:
        item = (
            f"- past_claim_id: {pc.claim_id}\n"
            f"  Outcome: the user {pc.outcome} this\n"
            f"  Claim: {pc.body}"
        )
        for line in format_precedent_lines(
            pc.outcome, pc.death_cause, pc.rationale, pc.revival_condition
        ):
            item += f"\n  {line}"
        past_items.append(item)
    past_block = "\n\n".join(past_items)

    user = (
        f"Current claim (being grilled now): {claim}\n\n"
        f"Prior-art papers (NOVELTY anchor):\n{papers_block}\n\n"
        f"The user's OWN past grilled claims (TASTE anchor):\n{past_block}\n\n"
        "First find the closest prior work and the most-similar past claim(s), "
        "then position the current claim on the taste/worth axis. Anchor every "
        "tier to a specific provided paper or past claim; if you cannot anchor "
        "it, leave the anchors empty."
    )
    return system, user


def build_semantic_edges_prompt(
    claim: str,
    candidates: list[tuple[str, str]],
) -> tuple[str, str]:
    """Judge typed semantic relationships from the CURRENT claim to candidates.

    Lens 第三刀 / ③ 可查询语料 (Tier 1, 持久语义图). The reviewer decides, for
    the CURRENT claim against each PROVIDED candidate claim, whether one of four
    typed relationships holds. Edges are recorded as ``LINK`` events and read
    back by the corpus_graph projection; they feed L4 threat detection (a killed
    dependency = an exposed foundation; centrality = builds_on in-degree).

    ``candidates``: ``(candidate_claim_body, candidate_claim_id)`` tuples — the
    other grilled claims pre-filtered by lexical overlap. Each must be cited by
    its EXACT provided id.

    Edge vocabulary (the ONLY four legal types; ``contradicts``/``grounds`` are
    handled elsewhere by ①/structure and are NOT in scope here):
    - ``builds_on``: the current claim EXTENDS or relies on the candidate's
      RESULT — it advances from where the candidate ended.
    - ``depends_on``: the current claim's VALIDITY rests on the candidate still
      holding — if the candidate were killed, the current claim is undermined.
    - ``shares_method``: both use the SAME method / approach / technique.
    - ``shares_gap``: both are blocked by the SAME unaddressed gap / open
      problem.

    ANTI-HALLUCINATION (mirrors the contradiction / taste prompts — the failure
    mode is OVER-connecting): assert an edge ONLY to a SPECIFIC provided
    candidate, cited by its exact id; NEVER invent a claim or an id. Skeptical
    default — MOST claim pairs have NO typed edge; when nothing genuinely holds,
    return an EMPTY list. Do NOT score or rank idea quality (取证不定见).
    """
    system = (
        "You analyze a researcher's CURRENT claim against several of their OWN "
        "past claims that they already grilled (each survived or was killed). "
        "Your ONLY job is to identify, for EACH provided candidate, whether one "
        "of four SPECIFIC typed relationships holds FROM the current claim TO "
        "that candidate.\n\n"
        "The four edge types (use ONLY these):\n"
        "- \"builds_on\": the current claim EXTENDS or relies on the candidate's "
        "RESULT — it advances from where the candidate ended.\n"
        "- \"depends_on\": the current claim's VALIDITY rests on the candidate "
        "still holding — if the candidate were false, the current claim would be "
        "undermined.\n"
        "- \"shares_method\": both claims use the SAME method, approach, or "
        "technique.\n"
        "- \"shares_gap\": both claims are blocked by the SAME unaddressed gap or "
        "open problem.\n\n"
        "ANTI-HALLUCINATION — THIS IS THE FAILURE MODE. Your default urge is to "
        "connect everything; that is WRONG and corrodes the graph. Follow these "
        "rules strictly:\n"
        "1. SKEPTICAL DEFAULT: MOST pairs of claims have NO typed relationship. "
        "Assert an edge ONLY when one of the four types GENUINELY and clearly "
        "holds. When in doubt, emit NOTHING for that candidate.\n"
        "2. CITE A REAL CANDIDATE: every edge MUST reference a candidate by its "
        "EXACT provided target_claim_id. NEVER invent a claim or an id, and "
        "NEVER reference a claim that was not provided.\n"
        "3. ONE TYPE PER EDGE: pick the single best-fitting type; do not emit "
        "multiple edges to the same candidate.\n"
        "4. NO QUALITY JUDGMENT: do NOT score, rank, praise, or criticize either "
        "claim. State only the structural relationship.\n\n"
        "If NO candidate has a genuine typed relationship, return an empty "
        "\"edges\" list.\n\n"
        "Respond ONLY with valid JSON in this exact format:\n"
        '{"edges": [{"target_claim_id": "<exact id of a provided candidate>", '
        '"edge_type": "builds_on" | "depends_on" | "shares_method" | '
        '"shares_gap", '
        '"reason": "<one sentence: where the relationship factually holds>"}]}\n\n'
        + OUTPUT_LANGUAGE_INSTRUCTION
    )

    if candidates:
        candidates_block = "\n\n".join(
            f"- target_claim_id: {cand_id}\n  Claim: {cand_body}"
            for cand_body, cand_id in candidates
        )
    else:
        candidates_block = "(none)"

    user = (
        f"Current claim (being analyzed now): {claim}\n\n"
        f"Candidate past claims (cite each by its exact target_claim_id):\n"
        f"{candidates_block}\n\n"
        "For each candidate, decide whether a builds_on / depends_on / "
        "shares_method / shares_gap relationship genuinely holds from the "
        "current claim to that candidate. Emit an edge ONLY when one clearly "
        "does; otherwise leave it out. Return an empty list if none hold."
    )
    return system, user


def build_verdict_prompt(
    claim: str, question: str, answer: str, evidence: str = ""
) -> tuple[str, str]:
    """Draft a verdict proposal (auto_verdict). 死因分诊: a kill proposal must
    triage the death cause (four-way enum) and a circumstantial kill must
    state a revival condition. The proposal is machine-drafted, human-signed
    — it still goes through the confirmed=False + CONFIRM gate."""
    system = (
        "You are a rigorous academic judge evaluating whether a claim survives "
        "a challenge. You must decide: does the answer adequately address the "
        "challenge question? Be strict but fair.\n\n"
        'If the outcome is "kill", you must also triage the DEATH CAUSE — pick '
        "exactly one:\n"
        '- "refuted": the claim is factually wrong (truth-axis kill; includes '
        "being a duplicate of an already-killed idea).\n"
        '- "not_worth": the claim is correct but not worth pursuing '
        "(worth-axis kill).\n"
        '- "boundary": the original formulation died, but the death drew a '
        "boundary — a narrowed version of the claim would survive.\n"
        '- "circumstantial": the claim did not conclusively die on any axis '
        "(it just could not be defended right now — missing material, "
        'missing proof). A circumstantial kill MUST include a concrete, '
        "checkable revival_condition under which the claim is worth "
        "reopening; if you cannot state one, the cause is not_worth, not "
        "circumstantial.\n\n"
        "Respond ONLY with valid JSON in this exact format:\n"
        '{"outcome": "survive" or "kill", '
        '"rationale": "<1-2 sentence justification>", '
        '"confidence": <0.0 to 1.0>, '
        '"death_cause": "refuted" | "not_worth" | "boundary" | '
        '"circumstantial" | null, '
        '"revival_condition": "<checkable condition>" | null}\n'
        'death_cause MUST be null when outcome is "survive" and one of the '
        'four causes when outcome is "kill". revival_condition MUST be null '
        'unless death_cause is "circumstantial".'
    )
    user = (
        f"Claim: {claim}\n\n"
        f"Challenge question: {question}\n\n"
        f"Answer provided: {answer}\n\n"
        "Does this answer adequately defend the claim against the challenge?"
    )
    if evidence:
        system += (
            "\n\nAlso weigh whether the answer is consistent with the provided "
            "literature evidence: an answer contradicted by the cited literature "
            "weighs toward kill, while one backed by it weighs toward survive. "
            "NOT_SUPPORTED entries are legacy judgments recorded before "
            "three-state grounding: the paper did not support the claim, but "
            "whether it was silent or contradicting was never recorded — do "
            "NOT weigh them as refutations."
        )
        user = (
            f"Claim: {claim}\n\n"
            f"Challenge question: {question}\n\n"
            f"Answer provided: {answer}\n\n"
            f"Literature evidence:\n{evidence}\n\n"
            "Does this answer adequately defend the claim against the challenge?"
        )
    system += "\n\n" + OUTPUT_LANGUAGE_INSTRUCTION
    return system, user
