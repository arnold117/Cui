"""Keeps scripts/canary_journey.py from rotting: pure check functions on canned data (no network, no LLM)."""
from scripts import canary_journey as cj


def test_empty_locator_check():
    assert cj.check_no_empty_locators([{"locator": "arxiv:2401.00001"}, {"locator": "doi:10.1/x"}])[0]
    assert not cj.check_no_empty_locators([{"locator": "arxiv:"}, {"locator": "arxiv:2401.00001"}])[0]


def test_camp_structure_check():
    assert not cj.check_related_work_not_claim_shaped(cj.CLAIM_TEXT, "一派认为A有效。另一派认为B无效。")[0]
    assert not cj.check_related_work_not_claim_shaped(cj.CLAIM_TEXT, cj.CLAIM_TEXT)[0]
    assert cj.check_related_work_not_claim_shaped(cj.CLAIM_TEXT, "已有工作从评测基准角度考察推理能力的变化 [arxiv:1]。")[0]


def test_anchor_and_flag_ratio():
    assert cj.check_anchored("x", "RLHF 与 Reasoning", cj.DEFAULT_CORE_TERMS)[0]
    assert not cj.check_anchored("x", "完全无关", cj.DEFAULT_CORE_TERMS)[0]
    assert cj.flagged_ratio([{"verdict": "supported"}, {"verdict": "unsupported"}]) == "1/2 flagged"
