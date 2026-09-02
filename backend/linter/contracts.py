"""Layer contracts for `make lint-contracts` — single source of truth.

Every rule below encodes spec-v5-merge S8/S13/S15 (kernel purity, machine
enforcement) as declared in docs/plan-v5-slice0.md §T4:

- kernel (domain/store incl. native research_universe domain/store/command_guard)
  must not import cui.llm, httpx, host (cui.api / research_universe.api), SDK
  (research_universe.application), plugins (challenge_generator, legacy_archive)
  or the LLM SDKs (openai/anthropic) / HTTP frameworks (fastapi/uvicorn/dotenv).
- cui.llm is a leaf: it must not depend on any business package.
- SDK (research_universe.application) must not depend on host, llm or plugins
  (host/plugins may import the SDK, never the reverse).

`python -m linter` (from backend/) expands the source packages to concrete
modules and runs import-linter against them.
"""

SESSION = {
    "root_package": "cui",
    "include_external_packages": True,
    # imports under typing.TYPE_CHECKING are annotations only, not runtime deps
    "exclude_type_checking_imports": True,
}

# Packages treated as kernel / state machine (zero LLM/HTTP/host/plugin).
KERNEL_PACKAGES = [
    "cui.domain",
    "cui.store",
    "cui.research_universe.domain",
    "cui.research_universe.store",
    "cui.research_universe.command_guard",
]

KERNEL_FORBIDDEN = [
    "cui.llm",
    "cui.api",
    "cui.research_universe.api",
    "cui.research_universe.application",
    "cui.research_universe.challenge_generator",
    "cui.legacy_archive",
    # external: LLM SDKs, HTTP framework, env loader
    "httpx",
    "openai",
    "anthropic",
    "fastapi",
    "uvicorn",
    "dotenv",
]

LLM_LEAF_FORBIDDEN = [
    "cui.domain",
    "cui.store",
    "cui.research_universe",
    "cui.api",
    "cui.legacy_archive",
]

SDK_FORBIDDEN = [
    "cui.llm",
    "cui.api",
    "cui.research_universe.api",
    "cui.legacy_archive",
    "cui.research_universe.challenge_generator",
]

CONTRACTS = [
    {
        "name": "kernel purity: domain/store never import llm/httpx/host/plugin",
        "type": "forbidden",
        "source_packages": KERNEL_PACKAGES,
        "forbidden_imports": KERNEL_FORBIDDEN,
    },
    {
        "name": "cui.llm is a leaf: never imports business packages",
        "type": "forbidden",
        "source_packages": ["cui.llm"],
        "forbidden_imports": LLM_LEAF_FORBIDDEN,
    },
    {
        "name": "SDK never depends on host/llm/plugins (reverse imports are the point)",
        "type": "forbidden",
        "source_packages": ["cui.research_universe.application"],
        "forbidden_imports": SDK_FORBIDDEN,
    },
]
