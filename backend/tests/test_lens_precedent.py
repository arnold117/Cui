"""Tests for select_kill_precedents — 判例先验 selection (pure, deterministic).

Spec: docs/spec-precedent-prior.md §2 Q3/Q4 + §4 acceptance 2 & 6.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from anneal.lens.precedent import (
    PRECEDENT_BUDGET,
    DatedPrecedent,
    select_kill_precedents,
)
from anneal.llm.prompts import ClaimPrecedent

T0 = datetime(2026, 1, 1)


def _dated(
    claim_id: str,
    *,
    outcome: str = "killed",
    minutes: int = 0,
    death_cause: str | None = "refuted",
    body: str = "some claim",
) -> DatedPrecedent:
    return DatedPrecedent(
        ts=T0 + timedelta(minutes=minutes),
        precedent=ClaimPrecedent(
            body=body,
            outcome=outcome,
            claim_id=claim_id,
            death_cause=death_cause if outcome == "killed" else None,
            rationale="because",
        ),
    )


class TestKillOnly:
    def test_survive_precedents_are_dropped(self):
        """前功赦免 excluded structurally — survive never reaches the prompt."""
        selected = select_kill_precedents(
            [
                _dated("c-kill", outcome="killed"),
                _dated("c-survive", outcome="survived"),
            ]
        )
        assert [p.claim_id for p in selected] == ["c-kill"]

    def test_all_survive_yields_empty(self):
        selected = select_kill_precedents(
            [_dated("a", outcome="survived"), _dated("b", outcome="survived")]
        )
        assert selected == []

    def test_empty_input_yields_empty(self):
        assert select_kill_precedents([]) == []


class TestOrdering:
    def test_most_recent_first(self):
        selected = select_kill_precedents(
            [_dated("old", minutes=0), _dated("new", minutes=10), _dated("mid", minutes=5)]
        )
        assert [p.claim_id for p in selected] == ["new", "mid", "old"]

    def test_ties_broken_deterministically_by_claim_id(self):
        """Same ts must not make the result depend on enumeration order."""
        one_order = select_kill_precedents(
            [_dated("a", minutes=3), _dated("b", minutes=3), _dated("c", minutes=3)]
        )
        other_order = select_kill_precedents(
            [_dated("c", minutes=3), _dated("a", minutes=3), _dated("b", minutes=3)]
        )
        assert [p.claim_id for p in one_order] == [p.claim_id for p in other_order]


class TestBudget:
    def test_budget_is_twelve(self):
        assert PRECEDENT_BUDGET == 12

    def test_keeps_the_twelve_most_recent(self):
        """>12 precedents: ts 倒序取最近 12 — deterministic, assertable."""
        candidates = [_dated(f"c-{i:02d}", minutes=i) for i in range(20)]
        selected = select_kill_precedents(candidates)

        assert len(selected) == PRECEDENT_BUDGET
        assert [p.claim_id for p in selected] == [
            f"c-{i:02d}" for i in range(19, 7, -1)
        ]
        # The oldest eight are gone, the newest is in.
        ids = {p.claim_id for p in selected}
        assert "c-00" not in ids
        assert "c-19" in ids

    def test_survive_does_not_consume_budget(self):
        """Dropped survive precedents must not push out real kills."""
        candidates = [_dated(f"kill-{i:02d}", minutes=i) for i in range(12)]
        candidates += [
            _dated(f"survive-{i:02d}", outcome="survived", minutes=100 + i)
            for i in range(5)
        ]
        selected = select_kill_precedents(candidates)

        assert len(selected) == 12
        assert all(p.outcome == "killed" for p in selected)

    def test_budget_override(self):
        candidates = [_dated(f"c-{i}", minutes=i) for i in range(5)]
        assert len(select_kill_precedents(candidates, budget=2)) == 2

    def test_under_budget_returns_everything(self):
        candidates = [_dated(f"c-{i}", minutes=i) for i in range(3)]
        assert len(select_kill_precedents(candidates)) == 3
