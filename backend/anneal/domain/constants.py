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
