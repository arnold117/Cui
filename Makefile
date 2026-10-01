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
