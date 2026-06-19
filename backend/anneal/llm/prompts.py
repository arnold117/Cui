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
