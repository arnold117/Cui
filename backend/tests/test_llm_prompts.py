from anneal.domain.events import GROUND, make_event
from anneal.llm.prompts import (
    build_challenge_prompt,
    build_grounding_prompt,
    build_verdict_prompt,
    format_evidence_block,
    truncate_rationale,
)


def _ground(verdict: str, **payload):
    """A new-style GROUND event carrying the three-state verdict."""
    base = {"verdict": verdict, "source": "arxiv", "title": "Paper X"}
    base.update(payload)
    return make_event(type=GROUND, actor="system", target_ref="claim-a", payload=base)


def _legacy_ground(supported: bool, **payload):
    """A legacy GROUND event carrying only the binary `supported` bool."""
    base = {"supported": supported, "source": "arxiv", "title": "Paper X"}
    base.update(payload)
    return make_event(type=GROUND, actor="system", target_ref="claim-a", payload=base)


class TestFormatEvidenceBlock:
    def test_empty_list_returns_empty_string(self):
        assert format_evidence_block([]) == ""

    def test_supports_formatting(self):
        g = _ground("supports", evidence="RCT showed effect", assessment="direct support")
        block = format_evidence_block([g])
        assert block == "- [SUPPORTS] arxiv:Paper X — RCT showed effect (direct support)"

    def test_contradicts_formatting(self):
        """contradicts evidence is explicitly labeled counter-evidence."""
        g = _ground("contradicts", evidence="null result", assessment="contradicts")
        block = format_evidence_block([g])
        assert block == "- [CONTRADICTS] arxiv:Paper X — null result (contradicts)"

    def test_silent_excluded_from_block(self):
        """查无 bears nothing on the claim — silent never enters the block."""
        g = _ground("silent", assessment="unrelated field")
        assert format_evidence_block([g]) == ""

    def test_legacy_true_reads_as_supports(self):
        g = _legacy_ground(True, evidence="RCT showed effect")
        block = format_evidence_block([g])
        assert block == "- [SUPPORTS] arxiv:Paper X — RCT showed effect"

    def test_legacy_false_labeled_not_supported_never_contradicts(self):
        """Legacy False is 未分态 — rendered honestly, NEVER upgraded to
        CONTRADICTS (silent-or-contradicts was never recorded)."""
        g = _legacy_ground(False, evidence="null result")
        block = format_evidence_block([g])
        assert block == "- [NOT_SUPPORTED] arxiv:Paper X — null result"
        assert "CONTRADICTS" not in block

    def test_omits_empty_evidence_and_assessment(self):
        g = _ground("supports", evidence="", assessment="")
        block = format_evidence_block([g])
        assert block == "- [SUPPORTS] arxiv:Paper X"

    def test_one_line_per_bearing_item(self):
        block = format_evidence_block(
            [_ground("supports"), _ground("contradicts"), _ground("silent")]
        )
        assert len(block.splitlines()) == 2  # silent contributes no line


class TestBuildGroundingPrompt:
    def test_returns_tuple_of_strings(self):
        system, user = build_grounding_prompt("c", "t", "abs")
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_user_contains_claim_title_abstract(self):
        system, user = build_grounding_prompt("X improves Y", "Paper T", "Abstract A")
        assert "X improves Y" in user
        assert "Paper T" in user
        assert "Abstract A" in user

    def test_json_schema_is_three_state_verdict(self):
        system, _ = build_grounding_prompt("c", "t", "a")
        assert '"verdict"' in system
        assert '"supports"' in system
        assert '"contradicts"' in system
        assert '"silent"' in system
        # The binary schema is gone — no boolean supported key remains.
        assert '"supported"' not in system

    def test_skeptical_default_stated(self):
        """拿不准 bear on 与否 → silent, never contradicts — spelled out."""
        system, _ = build_grounding_prompt("c", "t", "a")
        assert "SKEPTICAL DEFAULT" in system
        assert "Absence of support is NOT contradiction." in system

    def test_silent_is_first_class_not_failure(self):
        system, _ = build_grounding_prompt("c", "t", "a")
        assert "first-class" in system

    def test_json_instruction_present(self):
        system, _ = build_grounding_prompt("c", "t", "a")
        assert "JSON" in system


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
    # Includes the 死因分诊 (death-cause triage) instructions — the baseline
    # tracks the CURRENT no-evidence prompt so the evidence param alone never
    # mutates the base text.
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

    def test_legacy_not_supported_guidance_present(self):
        """The model is told NOT to treat legacy 未分态 entries as refutations."""
        system, _ = build_challenge_prompt("claim", "ctx", "- [NOT_SUPPORTED] a:b")
        assert "NOT_SUPPORTED" in system
        assert "do NOT treat them as refutations" in system


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

    def test_legacy_not_supported_guidance_present(self):
        system, _ = build_verdict_prompt("c", "q", "a", "- [NOT_SUPPORTED] a:b")
        assert "NOT_SUPPORTED" in system
        assert "NOT weigh them as refutations" in system


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


class TestTruncateRationale:
    """Deterministic 300-char cap for precedent injection (spec Q4)."""

    def test_short_rationale_verbatim(self):
        assert truncate_rationale("short") == "short"

    def test_exactly_limit_verbatim(self):
        text = "x" * 300
        assert truncate_rationale(text) == text

    def test_over_limit_truncated_with_ellipsis(self):
        text = "a" * 301
        out = truncate_rationale(text)
        assert out == "a" * 300 + "…"
        assert len(out) == 301

    def test_empty_string(self):
        assert truncate_rationale("") == ""

    def test_custom_limit(self):
        assert truncate_rationale("abcdef", limit=3) == "abc…"

    def test_deterministic(self):
        text = "b" * 999
        assert truncate_rationale(text) == truncate_rationale(text)


class TestVerdictPromptDeathTriage:
    def test_system_describes_all_four_causes(self):
        system, _ = build_verdict_prompt("c", "q", "a")
        for cause in ("refuted", "not_worth", "boundary", "circumstantial"):
            assert cause in system

    def test_json_schema_carries_triage_keys(self):
        system, _ = build_verdict_prompt("c", "q", "a")
        assert '"death_cause"' in system
        assert '"revival_condition"' in system

    def test_null_rules_stated(self):
        """death_cause null on survive / required on kill; revival only circumstantial."""
        system, _ = build_verdict_prompt("c", "q", "a")
        assert 'null when outcome is "survive"' in system
        assert 'unless death_cause is "circumstantial"' in system

    def test_no_revival_no_circumstantial_rule(self):
        """The escape valve is spelled out: no statable revival = not_worth."""
        system, _ = build_verdict_prompt("c", "q", "a")
        assert "cannot state one" in system
