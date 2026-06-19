from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anneal.domain.events import Event


def format_evidence_block(evidence_events: list[Event]) -> str:
    """Render confirmed GROUND events into a compact, LLM-readable block.

    One item per line:
      ``- [SUPPORTS] {source}:{title} — {evidence} ({assessment})``
    when ``payload["supported"]`` is truthy, ``[CONTRADICTS]`` otherwise.
    Empty evidence/assessment segments are omitted gracefully. An empty input
    list yields "" (callers treat "" as "no evidence" and keep the legacy
    prompt verbatim).
    """
    lines: list[str] = []
    for e in evidence_events:
        p = e.payload
        stance = "SUPPORTS" if p.get("supported") else "CONTRADICTS"
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
            "actually cover the claim's generalization."
        )
        user = (
            f"Claim: {claim}\n\nContext: {context}\n\n"
            f"Literature evidence:\n{evidence}\n\n"
            "Generate one focused challenge question for this claim."
        )
    return system, user


def build_grounding_prompt(claim: str, paper_title: str, paper_abstract: str) -> tuple[str, str]:
    system = (
        "You are a rigorous evidence assessor. Your job is to judge whether a "
        "research paper SUPPORTS a given claim, based solely on the paper's "
        "title and abstract. Do not invent evidence not present in the abstract. "
        "If the abstract does not bear on the claim, the claim is not supported.\n\n"
        "Respond ONLY with valid JSON in this exact format:\n"
        '{"supported": true or false, '
        '"evidence": "<short quote or paraphrase from the abstract that bears on '
        'the claim, or empty string if none>", '
        '"assessment": "<one-sentence rationale>"}'
    )
    user = (
        f"Claim: {claim}\n\n"
        f"Paper title: {paper_title}\n\n"
        f"Paper abstract: {paper_abstract}\n\n"
        "Does this paper support the claim?"
    )
    return system, user


def build_contradiction_prompt(
    current_claim: str, past_claim: str, past_outcome: str
) -> tuple[str, str]:
    """Judge whether the CURRENT claim conflicts with the user's OWN PAST claim.

    The past claim was already grilled by the user and either ``survived`` or
    ``killed`` (``past_outcome``). The reviewer identifies the *factual*
    relationship between the two claims and, if they conflict, poses a single
    challenge question grounded in that conflict.

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
    user = (
        f"Current claim (being grilled now): {current_claim}\n\n"
        f"Past claim (the user already {past_outcome} this one): {past_claim}\n\n"
        "Do these claims contradict, duplicate, or stand in tension? "
        "Identify the factual relationship and, if so, the challenge question."
    )
    return system, user


def build_taste_prompt(
    claim: str,
    prior_art_papers: list[dict],
    past_claims: list[tuple[str, str, str]],
) -> tuple[str, str]:
    """Position a CURRENT claim on the taste/worth axis (Lens 第二刀 / 品味锚).

    ``prior_art_papers``: neutral paper dicts (title/abstract/source_id) — the
    NOVELTY anchor. May be EMPTY (degraded: literature未对位).
    ``past_claims``: ``(claim_body, past_outcome, claim_id)`` tuples — the user's
    OWN grilled kill/survive record, the TASTE anchor. Guaranteed NON-empty
    (history is the gate; the service won't call this without history).

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
        "Respond ONLY with valid JSON in this exact format:\n"
        '{"tier": "replication" | "incremental" | "novel_but_tasteless" | '
        '"tasteful", '
        '"reasoning": "<relative positioning, NO scoring, name what is not '
        'novel>", '
        '"anchored_papers": [{"title": "<exact title of a provided paper>"}], '
        '"anchored_claims": [{"past_claim_id": "<id of a provided past claim>"}], '
        '"question": "<a refutable challenge, e.g. what is the worthwhile '
        'increment here?>"}'
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

    past_block = "\n\n".join(
        f"- past_claim_id: {claim_id}\n  Outcome: the user {outcome} this\n"
        f"  Claim: {body}"
        for body, outcome, claim_id in past_claims
    )

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
        '"reason": "<one sentence: where the relationship factually holds>"}]}'
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
    system = (
        "You are a rigorous academic judge evaluating whether a claim survives "
        "a challenge. You must decide: does the answer adequately address the "
        "challenge question? Be strict but fair.\n\n"
        "Respond ONLY with valid JSON in this exact format:\n"
        '{"outcome": "survive" or "kill", '
        '"rationale": "<1-2 sentence justification>", '
        '"confidence": <0.0 to 1.0>}'
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
            "weighs toward kill, while one backed by it weighs toward survive."
        )
        user = (
            f"Claim: {claim}\n\n"
            f"Challenge question: {question}\n\n"
            f"Answer provided: {answer}\n\n"
            f"Literature evidence:\n{evidence}\n\n"
            "Does this answer adequately defend the claim against the challenge?"
        )
    return system, user
