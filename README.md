# 淬 · Cui

**A research environment that argues with you, and never decides for you.**

Cui starts from a question, not a document. You explore the literature, write your own claims, and put them through adversarial review rounds: the system digs up supporting and contradicting evidence and raises challenges, and you rule on what lives and what dies. Every challenge, answer and verdict is kept as a trajectory, and that history is meant to compound into a personal **Lens**: a model of how *you* read papers and defend claims.

> **Status: early, under active development.** Solo project. The core loop works; the UI is mid-redesign, so expect rough edges and breaking changes. Feedback and arguments are welcome in [Issues](https://github.com/arnold117/Cui/issues).

## The one rule

> **Automate evidence-gathering. Never automate verdicts.**

The model searches, grounds, finds contradictions and attacks your claim. Only you decide whether it survives.

**Enforced in the code today:**

- **No machine-written verdicts.** No code path writes one, not even as a suggestion. A verdict is a user action and requires a written reason.
- **A verdict isn't a boolean:** survived, or one of four causes of death: refuted, not worth it, boundary, or circumstantial. Circumstantial requires a revival condition.
- **Evidence is supports / contradicts / silent / cannot assess.** "Nothing found" is a first-class result, kept apart from "couldn't tell": a failed parse is never recorded as silent.
- **Confirmed counter-evidence always gets raised.** Confirming a contradiction puts a challenge on the board from a fixed template, with no LLM call.
- ***Survived* means the claim held up this round, not that it's true**, and the UI says so.

**Design rules, not fully built yet:**

- **The attacker may read your history; the judge never does.** Only kills feed the challenger, never survivals. (Prototyped June–July 2026; archived in the redesign, not in the current code.)
- **Precedents are picked by cause of death, not topic.** A cause of death that recurs across topics is a habit of your method, and topic-overlap retrieval throws exactly those away.
- **No ghost-writing.** While an idea is still forming, the system asks and never drafts your claim. (The free-form claim path follows this; the guided literature mode doesn't yet.)
- **The Lens reads only gated trajectories.** (Not in the current code; parked ideas already live in a separate sealed store.)

Full write-up: [Automate the evidence, never the verdict](https://arnold117.github.io/blog/2026/automate-evidence-never-verdicts/)

## What works today

- **Question workspaces:** explore → write a claim → immutable review rounds (LLM challenges) → evidence candidates through the evidence gate → your verdict → landscape summary and gap list.
- **Literature dialogue:** a guided six-step session. Question → candidate hypotheses and search terms → the agent proposes papers (from your corpus, or arXiv / OpenAlex) with reasons → you pick → landscape summary → challenge from the literature → gap → related-work draft.

## Running locally

You need Python 3.11+, Node 20+, PostgreSQL, and an LLM key (Anthropic, or any OpenAI-compatible provider such as DeepSeek).

```bash
# backend
cd backend
pip install -e ".[llm,dev]"            # in a fresh venv / conda env
cp .env.example .env                   # fill in CUI_LLM_* and CUI_DATABASE_URL
export $(grep '^CUI_DATABASE_URL=' .env) && alembic upgrade head
uvicorn "cui.api.app:create_app" --factory --port 8000

# frontend (second terminal)
cd frontend
npm install && npm run dev             # proxies /api to :8000
```

- Tests: `cd backend && pytest`
- Layer contracts: `make lint-contracts`
- Real-LLM journey canary (makes paid API calls, not part of CI): `make canary-journey`

## Architecture

- **kernel:** events, fences, projections, gates. No LLM or HTTP imports, checked by import-linter (`make lint-contracts`).
- **SDK:** Python interfaces plus a thin REST adapter (FastAPI).
- **host and plugins:** LLM providers, literature search, and the React + TypeScript UI.

Every claim's history is an append-only event stream, and its status is computed from those events, never stored.

## Docs

The design docs are mostly in Chinese.

- [Domain glossary](CONTEXT.md): the vocabulary behind the rules above (it also covers concepts from the archived June–July prototype)
- [Product requirements](docs/prd-research-universe.md) · [MVP spec](docs/spec-research-universe-mvp.md) · [UX spec](docs/spec-research-universe-ux.md) · [Visual spec](docs/spec-research-universe-visual.md)
- Development notes: [v5 merge spec](docs/spec-v5-merge.md) · [handoff](docs/v5-handoff.md) · [slice0 plan](docs/plan-v5-slice0.md) · [slice1 plan](docs/plan-v5-slice1.md)
- [Historical specs](docs/archive/pre-research-universe/)

## History

Cui (formerly [LitScribe](https://github.com/arnold117/LitScribe), a literature-review engine) has been in development since January 2026. The current version is a redesign started in June 2026.

## License

MIT
