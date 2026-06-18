from __future__ import annotations

def build_challenge_prompt(claim: str, context: str) -> tuple[str, str]:
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


def build_verdict_prompt(claim: str, question: str, answer: str) -> tuple[str, str]:
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
    return system, user
