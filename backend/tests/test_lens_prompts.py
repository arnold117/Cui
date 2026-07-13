"""Tests for build_contradiction_prompt — shape + the taste red line."""

from __future__ import annotations

from anneal.llm.prompts import build_contradiction_prompt


class TestBuildContradictionPrompt:
    def test_includes_both_claims_and_outcome(self) -> None:
        system, user = build_contradiction_prompt(
            "X increases Y", "X has no effect on Y", "survived"
        )
        assert "X increases Y" in user
        assert "X has no effect on Y" in user
        assert "survived" in user

    def test_killed_outcome_surfaces(self) -> None:
        _system, user = build_contradiction_prompt("A", "B", "killed")
        assert "killed" in user

    def test_demands_json(self) -> None:
        system, _user = build_contradiction_prompt("a", "b", "survived")
        assert "JSON" in system
        for key in ("contradicts", "tension_type", "tension", "question"):
            assert key in system

    def test_describes_tension_types(self) -> None:
        system, _user = build_contradiction_prompt("a", "b", "survived")
        assert "hard" in system
        assert "duplicate" in system
        assert "soft" in system

    def test_forbids_taste_scoring(self) -> None:
        """Red line: the system prompt must forbid quality/taste judgment."""
        system, _user = build_contradiction_prompt("a", "b", "survived")
        low = system.lower()
        assert "must not" in low or "not score" in low.replace("must not", "")
        # explicit ban vocabulary present
        assert "quality" in low
        assert "score" in low


class TestContradictionPrecedentInjection:
    """判例注入 (spec-verdict-precedent §2 Q4): the past verdict's quadruple
    rides into the pairwise prompt; the death cause lowers false positives."""

    def test_no_precedent_keeps_legacy_prompt_verbatim(self) -> None:
        legacy = build_contradiction_prompt("a", "b", "survived")
        explicit = build_contradiction_prompt(
            "a", "b", "survived",
            past_death_cause=None, past_rationale="", past_revival_condition=None,
        )
        assert legacy == explicit
        _system, user = legacy
        assert "Past verdict precedent" not in user

    def test_killed_not_worth_quadruple_in_user(self) -> None:
        _system, user = build_contradiction_prompt(
            "a", "b", "killed",
            past_death_cause="not_worth",
            past_rationale="correct but a dead-end direction",
        )
        assert "Past verdict precedent" in user
        assert "not_worth" in user
        assert "correct but a dead-end direction" in user

    def test_rationale_truncated_at_300_chars(self) -> None:
        long_rationale = "R" * 400
        _system, user = build_contradiction_prompt(
            "a", "b", "killed",
            past_death_cause="refuted", past_rationale=long_rationale,
        )
        assert "R" * 300 + "…" in user
        assert "R" * 301 not in user

    def test_circumstantial_carries_revival_condition(self) -> None:
        _system, user = build_contradiction_prompt(
            "a", "b", "killed",
            past_death_cause="circumstantial",
            past_rationale="cannot defend today",
            past_revival_condition="Tier 1 proof insufficient + embedding accepted",
        )
        assert "Revival condition" in user
        assert "Tier 1 proof insufficient + embedding accepted" in user

    def test_non_circumstantial_never_carries_revival(self) -> None:
        """spec Q4: revival_condition 仅偶然死 — never injected otherwise."""
        _system, user = build_contradiction_prompt(
            "a", "b", "killed",
            past_death_cause="refuted",
            past_rationale="just wrong",
            past_revival_condition="should never appear",
        )
        assert "should never appear" not in user

    def test_legacy_kill_marked_unclassified(self) -> None:
        """Legacy verdict (no recorded cause) → 死因未分类, never invented."""
        _system, user = build_contradiction_prompt(
            "a", "b", "killed", past_rationale="old kill",
        )
        assert "unclassified" in user

    def test_survived_precedent_has_rationale_but_no_death_cause(self) -> None:
        _system, user = build_contradiction_prompt(
            "a", "b", "survived", past_rationale="well defended",
        )
        assert "well defended" in user
        assert "Death cause" not in user

    def test_system_gains_false_positive_guidance(self) -> None:
        """② 降误报: taste-killed + similar ≠ hard contradiction."""
        system, _user = build_contradiction_prompt(
            "a", "b", "killed",
            past_death_cause="not_worth", past_rationale="r",
        )
        low = system.lower()
        assert "death cause" in low
        assert "not_worth" in system
        assert "not a logical contradiction" in low

    def test_red_line_survives_precedent_injection(self) -> None:
        """The no-scoring red line stays intact with precedent present."""
        system, _user = build_contradiction_prompt(
            "a", "b", "killed",
            past_death_cause="not_worth", past_rationale="r",
        )
        low = system.lower()
        assert "quality" in low
        assert "score" in low
