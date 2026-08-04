"""Opt-in live Slice 1 challenge canary; never loads .env."""
from __future__ import annotations
import os
import pytest
from anneal.llm.client import create_client
from anneal.llm.config import LLMConfig
from anneal.research_universe.challenge_generator import RealChallengeGenerator

_REQUIRED=("CUI_LLM_KEY","CUI_LLM_MODEL")
pytestmark=pytest.mark.skipif(not all(os.getenv(k) for k in _REQUIRED), reason="live canary skipped: CUI_LLM_KEY or CUI_LLM_MODEL absent from inherited environment")

@pytest.mark.live
def test_bilingual_narrow_challenge_canary():
    config=LLMConfig(provider=os.getenv("CUI_LLM_PROVIDER", "anthropic"), api_key=os.environ["CUI_LLM_KEY"], model=os.environ["CUI_LLM_MODEL"], base_url=os.getenv("CUI_LLM_BASE_URL") or None)
    generator=RealChallengeGenerator(create_client(config), config.model)
    for question,claim,needle in [("Does spaced repetition improve long-term retention?", "Spaced repetition improves long-term retention for all learners.", "retention"), ("绿化是否会降低城市夏季热岛强度？", "增加绿化一定会降低所有城区的夏季热岛强度。", "热")]:
        draft=generator.generate(question=question, claim=claim)
        assert all((draft.attack_surface, draft.why_it_matters, draft.self_check_method, draft.uncertainty))
        assert draft.prompt_version and draft.model_identifier == config.model
        assert draft.basis_refs == ["review_round.question_snapshot", "review_round.claim_snapshot"]
        fields=(draft.attack_surface, draft.why_it_matters, draft.self_check_method)
        for field in fields:
            letters=[ch for ch in field if ch.isalpha()]
            assert len(field.strip()) >= 20 and len(letters) >= 12
            if needle == "热":
                cjk=sum("一" <= ch <= "鿿" for ch in letters)
                assert cjk / len(letters) >= .30
            else:
                latin=sum(ch.isascii() and ch.isalpha() for ch in letters)
                assert latin / len(letters) >= .70
        assert "verdict" not in draft.attack_surface.lower() and "direction" not in draft.attack_surface.lower()
