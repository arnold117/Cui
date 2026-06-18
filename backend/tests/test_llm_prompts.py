from anneal.domain.events import GROUND, make_event
from anneal.llm.prompts import (
    build_challenge_prompt,
    build_verdict_prompt,
    format_evidence_block,
)


def _ground(supported: bool, **payload):
    base = {"supported": supported, "source": "arxiv", "title": "Paper X"}
    base.update(payload)
    return make_event(type=GROUND, actor="system", target_ref="claim-a", payload=base)


class TestFormatEvidenceBlock:
    def test_empty_list_returns_empty_string(self):
        assert format_evidence_block([]) == ""

    def test_supports_formatting(self):
        g = _ground(True, evidence="RCT showed effect", assessment="direct support")
        block = format_evidence_block([g])
        assert block == "- [SUPPORTS] arxiv:Paper X — RCT showed effect (direct support)"

    def test_contradicts_formatting(self):
        g = _ground(False, evidence="null result", assessment="contradicts")
        block = format_evidence_block([g])
        assert block == "- [CONTRADICTS] arxiv:Paper X — null result (contradicts)"

    def test_omits_empty_evidence_and_assessment(self):
        g = _ground(True, evidence="", assessment="")
        block = format_evidence_block([g])
        assert block == "- [SUPPORTS] arxiv:Paper X"

    def test_one_line_per_item(self):
        block = format_evidence_block([_ground(True), _ground(False)])
        assert len(block.splitlines()) == 2


# Pre-change reference output — these MUST stay byte-identical when evidence="".


def _challenge_baseline(claim: str, context: str) -> tuple[str, str]:
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


def _verdict_baseline(claim: str, question: str, answer: str) -> tuple[str, str]:
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


class TestBackwardCompat:
    def test_challenge_no_evidence_is_byte_identical(self):
        assert build_challenge_prompt("X improves Y", "bg") == _challenge_baseline(
            "X improves Y", "bg"
        )

    def test_challenge_default_arg_matches_explicit_empty(self):
        assert build_challenge_prompt("c", "ctx") == build_challenge_prompt("c", "ctx", "")

    def test_verdict_no_evidence_is_byte_identical(self):
        assert build_verdict_prompt("c", "q", "a") == _verdict_baseline("c", "q", "a")

    def test_verdict_default_arg_matches_explicit_empty(self):
        assert build_verdict_prompt("c", "q", "a") == build_verdict_prompt("c", "q", "a", "")


class TestChallengeWithEvidence:
    def test_user_contains_evidence_and_label(self):
        ev = "- [CONTRADICTS] arxiv:Paper X — null result (contradicts)"
        system, user = build_challenge_prompt("claim", "ctx", ev)
        assert "Literature evidence:" in user
        assert ev in user

    def test_system_augmented_with_grounding_instruction(self):
        ev = "- [SUPPORTS] arxiv:Paper X"
        system, _ = build_challenge_prompt("claim", "ctx", ev)
        assert "CONTRADICTS" in system
        assert "SUPPORTS" in system

    def test_json_schema_unchanged(self):
        system, _ = build_challenge_prompt("claim", "ctx", "- [SUPPORTS] a:b")
        assert '"target_aspect"' in system


class TestVerdictWithEvidence:
    def test_user_contains_evidence_and_label(self):
        ev = "- [SUPPORTS] arxiv:Paper X — RCT (support)"
        system, user = build_verdict_prompt("c", "q", "a", ev)
        assert "Literature evidence:" in user
        assert ev in user

    def test_system_augmented_with_literature_weighing(self):
        system, _ = build_verdict_prompt("c", "q", "a", "- [SUPPORTS] a:b")
        assert "literature" in system.lower()

    def test_json_schema_unchanged(self):
        system, _ = build_verdict_prompt("c", "q", "a", "- [SUPPORTS] a:b")
        assert '"outcome"' in system


class TestBuildChallengePrompt:
    def test_challenge_prompt_returns_tuple_of_strings(self):
        system, user = build_challenge_prompt("claim", "context")
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_challenge_prompt_contains_claim_and_context(self):
        system, user = build_challenge_prompt("X improves Y", "some background")
        assert "X improves Y" in user
        assert "some background" in user

    def test_challenge_prompt_system_contains_json_instruction(self):
        system, user = build_challenge_prompt("claim", "ctx")
        assert "JSON" in system


class TestBuildVerdictPrompt:
    def test_verdict_prompt_returns_tuple_of_strings(self):
        system, user = build_verdict_prompt("claim", "question", "answer")
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_verdict_prompt_contains_all_inputs(self):
        system, user = build_verdict_prompt("my claim", "my question", "my answer")
        assert "my claim" in user
        assert "my question" in user
        assert "my answer" in user

    def test_verdict_prompt_system_contains_json_instruction(self):
        system, user = build_verdict_prompt("c", "q", "a")
        assert "JSON" in system
