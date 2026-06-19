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
