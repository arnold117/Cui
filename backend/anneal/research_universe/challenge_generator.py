"""Narrow real LLM adapters: Slice 1 first challenge, Slice 6 additional
challenges and evidence candidate generation.

Every adapter here only ever reads native snapshots (round question/claim,
material excerpt).  Legacy Lens data must never enter these prompts.
"""
from __future__ import annotations
from anneal.llm.client import LLMClient
from anneal.research_universe.application import ChallengeDraft, EvidenceCandidateDraft

PROMPT_VERSION = "slice1-narrow-challenge-v1"
EXPANDED_CHALLENGE_PROMPT_VERSION = "slice6-expanded-challenge-v1"
EVIDENCE_CANDIDATE_PROMPT_VERSION = "slice6-evidence-candidate-v1"

SYSTEM = """You are Cui's adversarial reviewer. Return a JSON object only, with exactly: attack_surface, why_it_matters, self_check_method, uncertainty. Attack one specific inferential weakness in the claim against the stated question. self_check_method must be a concrete method the user can perform. Write attack_surface, why_it_matters, and self_check_method in the same language as the user-authored claim. Never supply a claim, verdict, answer, or direction."""

SYSTEM_EXPANDED = """You are Cui's adversarial reviewer. Return a JSON object only, with exactly: attack_surface, why_it_matters, self_check_method, uncertainty.

The user has already been challenged on the listed attack surfaces. Attack ONE specific inferential weakness in the claim against the stated question, choosing an angle that is NOT already covered by any already-used attack surface. Do not repeat or paraphrase an existing attack surface.

Be concrete and rigorous: name the specific inferential weakness (a missing control, an unstated scope boundary, an equivocation, a causal attribution that the evidence cannot carry, an unexamined prior, a measurement that cannot support the conclusion), and give a self_check_method the user can actually perform to test it. Do not ask for a claim, verdict, answer, or direction — the user's judgment is the product, never your own.

Write attack_surface, why_it_matters, and self_check_method in the same language as the user-authored claim."""

SYSTEM_EVIDENCE = """You are Cui's evidence screener. Return a JSON object only, with exactly: relation, rationale, evidence_highlight, uncertainty.

relation must be one of:
- "supports"      the material excerpt corroborates the claim;
- "contradicts"   the material excerpt undercuts the claim;
- "silent"        the material does not address the claim at all;
- "cannot_assess" you cannot determine the relation.

rationale explains WHY in the same language as the claim. evidence_highlight quotes the single most load-bearing phrase from the material excerpt (keep the original language of the excerpt). uncertainty is a short phrase describing how confident you are.

If the material's parse_status is "failed", relation MUST be "cannot_assess" — a material that failed to parse cannot be read, so it can never be assessed as silent, supporting, or contradicting. Never supply a claim, verdict, answer, or direction."""


class RealChallengeGenerator:
    def __init__(self, client: LLMClient, model_identifier: str | None) -> None:
        self.client, self.model_identifier = client, model_identifier
    def generate(self, *, question: str, claim: str) -> ChallengeDraft:
        data = self.client.complete_json(SYSTEM, f"Question:\n{question}\n\nUser-authored claim:\n{claim}")
        required = ("attack_surface", "why_it_matters", "self_check_method", "uncertainty")
        if set(data) != set(required) or not all(isinstance(data[key], str) and data[key].strip() for key in required):
            raise ValueError("model response is not the Slice 1 challenge schema")
        return ChallengeDraft(attack_surface=data["attack_surface"], why_it_matters=data["why_it_matters"], self_check_method=data["self_check_method"], uncertainty=data["uncertainty"], prompt_version=PROMPT_VERSION, model_identifier=self.model_identifier, basis_refs=["review_round.question_snapshot", "review_round.claim_snapshot"])
    def generate_additional(self, *, question: str, claim: str, prior_attack_surfaces: list[str]) -> ChallengeDraft:
        used = "\n- ".join(prior_attack_surfaces) if prior_attack_surfaces else "(none yet)"
        user = f"Question:\n{question}\n\nUser-authored claim:\n{claim}\n\nAlready-used attack surfaces (attack a DIFFERENT angle; never repeat one):\n- {used}"
        data = self.client.complete_json(SYSTEM_EXPANDED, user)
        required = ("attack_surface", "why_it_matters", "self_check_method", "uncertainty")
        if set(data) != set(required) or not all(isinstance(data[key], str) and data[key].strip() for key in required):
            raise ValueError("model response is not the Slice 6 expanded challenge schema")
        return ChallengeDraft(attack_surface=data["attack_surface"], why_it_matters=data["why_it_matters"], self_check_method=data["self_check_method"], uncertainty=data["uncertainty"], prompt_version=EXPANDED_CHALLENGE_PROMPT_VERSION, model_identifier=self.model_identifier, basis_refs=["review_round.question_snapshot", "review_round.claim_snapshot"])


class RealEvidenceCandidateGenerator:
    def __init__(self, client: LLMClient, model_identifier: str | None) -> None:
        self.client, self.model_identifier = client, model_identifier
    def generate(self, *, claim: str, material_excerpt: str, parse_status: str) -> EvidenceCandidateDraft:
        user = f"Claim:\n{claim}\n\nMaterial excerpt:\n{material_excerpt}\n\nMaterial parse_status: {parse_status}"
        data = self.client.complete_json(SYSTEM_EVIDENCE, user)
        required = ("relation", "rationale", "evidence_highlight", "uncertainty")
        if set(data) != set(required):
            raise ValueError("model response is not the Slice 6 evidence candidate schema")
        relation = data["relation"]
        if not isinstance(relation, str) or relation not in ("supports", "contradicts", "silent", "cannot_assess"):
            raise ValueError("model evidence relation is not legal")
        def _text(value: object) -> str | None:
            if not isinstance(value, str) or not value.strip():
                return None
            return value.strip()
        # The service replaces basis_refs with the concrete [material_id]; this
        # draft placeholder keeps the payload contract uniform.
        return EvidenceCandidateDraft(relation=relation, rationale=_text(data["rationale"]), evidence_highlight=_text(data["evidence_highlight"]), uncertainty=_text(data["uncertainty"]), prompt_version=EVIDENCE_CANDIDATE_PROMPT_VERSION, model_identifier=self.model_identifier, basis_refs=[])
