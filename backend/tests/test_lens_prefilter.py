"""Pure tests for anneal.lens.topic_terms + anneal.lens.prefilter."""

from __future__ import annotations

from anneal.domain.models import Claim
from anneal.lens.prefilter import prefilter_candidates
from anneal.lens.topic_terms import topic_terms


# ---------------------------------------------------------------------------
# topic_terms
# ---------------------------------------------------------------------------


class TestTopicTerms:
    def test_lowercases_and_tokenizes(self) -> None:
        assert topic_terms("Transformers Attention") == {"transformers", "attention"}

    def test_drops_stopwords(self) -> None:
        terms = topic_terms("the attention is all you need")
        assert "the" not in terms
        assert "is" not in terms
        assert "you" not in terms
        assert "attention" in terms
        assert "need" in terms

    def test_drops_generic_research_words(self) -> None:
        terms = topic_terms("our study shows the proposed model improves accuracy")
        # generic prose words filtered
        assert "study" not in terms
        assert "shows" not in terms
        assert "proposed" not in terms
        assert "model" not in terms
        # discriminative terms kept
        assert "improves" in terms
        assert "accuracy" in terms

    def test_drops_short_tokens(self) -> None:
        terms = topic_terms("ML is ok as an AI go")
        # tokens < 3 chars dropped
        assert "ml" not in terms
        assert "ai" not in terms
        assert "go" not in terms

    def test_empty_string(self) -> None:
        assert topic_terms("") == set()

    def test_deterministic(self) -> None:
        text = "Quantum annealing outperforms classical solvers on sparse graphs"
        assert topic_terms(text) == topic_terms(text)


# ---------------------------------------------------------------------------
# prefilter_candidates
# ---------------------------------------------------------------------------


def _claim(cid: str, body: str) -> Claim:
    return Claim(id=cid, library_id="lib-1", body=body)


class TestPrefilter:
    def test_ranks_by_overlap(self) -> None:
        current = "transformers improve machine translation quality"
        cands = [
            _claim("low", "neural networks playing chess"),  # 0 overlap → dropped
            _claim("high", "transformers boost translation quality across languages"),
            _claim("mid", "machine translation needs large corpora"),
        ]
        out = prefilter_candidates(current, cands)
        # high shares {transformers, translation, quality}, mid shares {translation}
        assert [c.id for c in out] == ["high", "mid"]

    def test_zero_overlap_dropped(self) -> None:
        current = "quantum annealing on sparse graphs"
        cands = [_claim("x", "photosynthesis in marine algae")]
        assert prefilter_candidates(current, cands) == []

    def test_top_k_cap(self) -> None:
        current = "attention mechanism in language models"
        cands = [
            _claim(f"c{i}", "attention language mechanism")
            for i in range(20)
        ]
        out = prefilter_candidates(current, cands, top_k=3)
        assert len(out) == 3

    def test_ties_broken_by_id_deterministic(self) -> None:
        current = "attention language model"
        # all share the same overlap → tie broken by id ascending
        cands = [
            _claim("zeta", "attention language framework"),
            _claim("alpha", "attention language framework"),
            _claim("mu", "attention language framework"),
        ]
        out = prefilter_candidates(current, cands)
        assert [c.id for c in out] == ["alpha", "mu", "zeta"]

    def test_order_independent(self) -> None:
        current = "transformers improve translation"
        a = _claim("a", "transformers help translation a lot")
        b = _claim("b", "translation benchmarks")
        assert [c.id for c in prefilter_candidates(current, [a, b])] == [
            c.id for c in prefilter_candidates(current, [b, a])
        ]

    def test_empty_current_returns_empty(self) -> None:
        cands = [_claim("a", "transformers translation")]
        assert prefilter_candidates("", cands) == []
