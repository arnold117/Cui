PY ?= python

.PHONY: lint-contracts
## Machine-enforce the kernel/SDK/llm layer contracts (backend/, needs cui env)
lint-contracts:
	cd backend && $(PY) -m linter
