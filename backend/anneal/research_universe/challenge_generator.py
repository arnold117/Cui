"""Narrow real LLM adapter for Slice 1 challenge generation."""
from __future__ import annotations
from anneal.llm.client import LLMClient
from anneal.research_universe.application import ChallengeDraft

PROMPT_VERSION = "slice1-narrow-challenge-v1"
SYSTEM = """You are Cui's adversarial reviewer. Return a JSON object only, with exactly: attack_surface, why_it_matters, self_check_method, uncertainty. Attack one specific inferential weakness in the claim against the stated question. self_check_method must be a concrete method the user can perform. Write attack_surface, why_it_matters, and self_check_method in the same language as the user-authored claim. Never supply a claim, verdict, answer, or direction."""

class RealChallengeGenerator:
    def __init__(self, client: LLMClient, model_identifier: str | None) -> None:
        self.client, self.model_identifier = client, model_identifier
    def generate(self, *, question: str, claim: str) -> ChallengeDraft:
        data = self.client.complete_json(SYSTEM, f"Question:\n{question}\n\nUser-authored claim:\n{claim}")
        required = ("attack_surface", "why_it_matters", "self_check_method", "uncertainty")
        if set(data) != set(required) or not all(isinstance(data[key], str) and data[key].strip() for key in required):
            raise ValueError("model response is not the Slice 1 challenge schema")
        return ChallengeDraft(attack_surface=data["attack_surface"], why_it_matters=data["why_it_matters"], self_check_method=data["self_check_method"], uncertainty=data["uncertainty"], prompt_version=PROMPT_VERSION, model_identifier=self.model_identifier, basis_refs=["review_round.question_snapshot", "review_round.claim_snapshot"])
