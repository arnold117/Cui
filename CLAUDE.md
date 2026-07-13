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
