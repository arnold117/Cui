PY ?= python

.PHONY: lint-contracts
## Machine-enforce the kernel/SDK/llm layer contracts (backend/, needs cui env)
lint-contracts:
	cd backend && $(PY) -m linter

.PHONY: contract
## Regenerate OpenAPI snapshot + frontend TS types (backend schema is the single source; pytest checks the snapshot is fresh)
contract:
	cd backend && $(PY) -m scripts.dump_openapi
	cd frontend && npx openapi-typescript src/features/research-universe/openapi.json --default-non-nullable false -o src/features/research-universe/api.gen.ts

.PHONY: canary-journey
## Manual real-LLM + real-search six-step dialogue sentinel (costs LLM calls + network; NOT in CI)
canary-journey:
	cd backend && $(PY) -m scripts.canary_journey
