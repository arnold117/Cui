# Cui (淬)

AI-native writing engine. Grills ideas, accumulates trajectories, forges drafts from verified claims.

## Architecture principles

- **Thought-centric, not document-centric.** The primary unit is an Idea (with trajectory), not a PDF or a draft.
- **Native rebuild, never retrofit.** New architecture is built from scratch; legacy pieces are cherry-picked only when they fit cleanly. No "link everything together" duct-taping.
- **Adversarial by default.** The system's job is to challenge, not to please. Bypass requires evidence.
- **Trajectory is the moat.** Every grilled session, every killed hypothesis, every pivot is a private asset that compounds into a personal Lens.

## Tech stack

- Python 3.11+ (backend)
- TypeScript / React (frontend)
- FastAPI (API layer)

## Development

- Use `conda activate anneal` (never install into base)
- `.env` is sacred — only edit `.env.example`
- Never use `EnterPlanMode` — it loses context
## v5 (2026-09-02)

- **v5 = LitScribe 融入 Cui 升级,slice0 执行中**。v5/slice0/merge 类任务先读 `docs/v5-handoff.md`(启动包)+ `docs/plan-v5-slice0.md`(任务清单);决策真相 `docs/spec-v5-merge.md`(已收敛,勿翻案)。

