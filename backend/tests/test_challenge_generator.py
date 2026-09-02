"""Schema validation unit tests for RealChallengeGenerator.

Regression (2026-09-02): current models often emit ``uncertainty`` as a JSON
number (a 0-1 confidence score) while the payload contract keeps it a string.
The validator must accept numbers (normalising them to str) and must keep
rejecting every malformed shape it rejected before.
"""
import json

import pytest

from cui.research_universe.challenge_generator import RealChallengeGenerator
from tests.fakes import FakeLLMClient


def _generator(raw_response: str) -> RealChallengeGenerator:
    return RealChallengeGenerator(FakeLLMClient([raw_response]), "test-model")


def _payload(**overrides) -> str:
    payload = {
        "attack_surface": "no control group",
        "why_it_matters": "causal claim unsupported by the design",
        "self_check_method": "rerun the study with a control arm",
        "uncertainty": "low",
    }
    payload.update(overrides)
    return json.dumps(payload)


# --- uncertainty tolerance (regression for numeric uncertainty) ---


def test_generate_accepts_float_uncertainty_as_string():
    draft = _generator(_payload(uncertainty=0.3)).generate(question="q?", claim="c.")
    assert draft.uncertainty == "0.3"


def test_generate_accepts_zero_uncertainty():
    # 0 is an int, not a bool — it is a legitimate (if extreme) confidence.
    draft = _generator(_payload(uncertainty=0)).generate(question="q?", claim="c.")
    assert draft.uncertainty == "0"


def test_generate_additional_accepts_int_uncertainty():
    draft = _generator(_payload(uncertainty=5)).generate_additional(
        question="q?", claim="c.", prior_attack_surfaces=["already used"])
    assert draft.uncertainty == "5"


def test_generate_keeps_string_uncertainty_unchanged():
    draft = _generator(_payload(uncertainty=" moderate ")).generate(question="q?", claim="c.")
    assert draft.uncertainty == "moderate"


# --- strictness retained: shapes rejected before must still raise ---


@pytest.mark.parametrize("overrides", [
    {"uncertainty": None},      # JSON null
    {"uncertainty": True},      # bool is an int subclass, not a confidence
    {"uncertainty": []},        # list
    {"uncertainty": {}},        # dict
    {"uncertainty": "   "},     # whitespace-only string
    {"extra_key": "x"},         # key set must be exactly the required four
    {"attack_surface": ""},     # empty text field
    {"why_it_matters": 3},      # non-string text field
])
def test_generate_rejects_malformed_payloads(overrides):
    with pytest.raises(ValueError):
        _generator(_payload(**overrides)).generate(question="q?", claim="c.")


def test_generate_additional_rejects_malformed_payloads():
    with pytest.raises(ValueError, match="Slice 6 expanded challenge"):
        _generator(_payload(uncertainty=None)).generate_additional(
            question="q?", claim="c.", prior_attack_surfaces=["already used"])


def test_generate_error_message_names_slice_1_schema():
    with pytest.raises(ValueError, match="Slice 1"):
        _generator(_payload(uncertainty="  ")).generate(question="q?", claim="c.")
