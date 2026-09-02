"""Shared domain constants."""

SUPPORTED_ARTIFACT_KINDS = {"idea", "review"}

# 死因分诊 (death-cause triage) — how a killed claim died. Kill is not a
# boolean: every NEW kill verdict must carry exactly one of these four causes
# (spec docs/spec-verdict-precedent.md §2). Legacy verdicts recorded before
# triage carry none; projections read that as "unclassified" — the enum itself
# has NO unclassified escape hatch for new data.
#   refuted        — truth-axis kill: the claim is factually wrong (terminal).
#   not_worth      — worth-axis kill: correct but not worth doing (terminal;
#                    the strongest revealed-taste signal).
#   boundary       — the original formulation died but drew a boundary; a
#                    narrowed successor claim may live on (successor_claim_id).
#   circumstantial — died on no axis (timing/resources); the ONLY non-terminal
#                    cause, MUST carry a revival_condition.
DEATH_CAUSES = {"refuted", "not_worth", "boundary", "circumstantial"}

# GROUND 判定三态 — how a collected paper bears on a claim. Not a boolean:
# "the literature is silent on this claim" and "the literature strikes this
# claim" are entirely different states (查无是一等输出，不是失败).
#   supports    — the abstract positively supports the claim.
#   contradicts — the abstract GENUINELY bears on the claim AND weakens or
#                 refutes it (怀疑默认: unsure whether it bears on the claim
#                 at all → silent, never contradicts).
#   silent      — the abstract does not bear on the claim.
# Legacy GROUND events carry only a `supported` bool: True reads as supports;
# False reads as "not_supported" (legacy 未分态 — silent-or-contradicts was
# never recorded and is NEVER guessed). New events write only `verdict`.
GROUND_VERDICTS = {"supports", "contradicts", "silent"}

# Read-side value for a legacy `supported: False` GROUND payload (未分态).
# NOT a member of GROUND_VERDICTS — no new event may ever be written with it.
GROUND_NOT_SUPPORTED = "not_supported"
