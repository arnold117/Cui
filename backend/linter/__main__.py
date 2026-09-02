"""Gate runner: expand contracts.py to import-linter config and run it.

Usage (from backend/): python -m linter
Exit code 0 = all layer contracts hold; 1 = violation (gate red).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from linter.contracts import CONTRACTS, SESSION


def _escape_basic(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _modules_of(packages: list[str]) -> list[str]:
    """Concrete module names for each source package (walk backend/cui on disk)."""
    backend_root = Path(__file__).resolve().parents[1]
    package_root = backend_root / "cui"
    modules: set[str] = set()
    for path in package_root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(package_root)
        parts = list(rel.parts[:-1]) + [rel.stem]
        if parts[-1] == "__init__":
            parts = parts[:-1]  # a package directory is its own module path
        modules.add(".".join(["cui", *parts]))
    missing = [pkg for pkg in packages if not any(name == pkg or name.startswith(pkg + ".") for name in modules)]
    if missing:
        raise SystemExit(f"contract source package not found under backend/cui: {missing}")
    return sorted(name for name in modules if any(name == pkg or name.startswith(pkg + ".") for pkg in packages))


def _render_toml() -> str:
    lines = ['[tool.importlinter]']
    for key, value in SESSION.items():
        rendered = value
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif isinstance(value, str):
            rendered = f'"{_escape_basic(value)}"'
        lines.append(f"{key} = {rendered}")
    for contract in CONTRACTS:
        lines.append("")
        lines.append('[[tool.importlinter.contracts]]')
        lines.append(f'name = "{_escape_basic(contract["name"])}"')
        lines.append(f'type = "{contract["type"]}"')
        sources = _modules_of(contract["source_packages"])
        forbid = sorted(contract["forbidden_imports"])
        lines.append("source_modules = [" + ", ".join(f'"{_escape_basic(s)}"' for s in sources) + "]")
        lines.append("forbidden_modules = [" + ", ".join(f'"{_escape_basic(f)}"' for f in forbid) + "]")
    return "\n".join(lines) + "\n"


def main() -> int:
    config = _render_toml()
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as handle:
        handle.write(config)
        config_path = handle.name
    try:
        import importlinter.cli  # noqa: F401 — registers option readers / contract types
        from importlinter.application import use_cases
        ok = use_cases.lint_imports(config_filename=config_path, no_logo=True)
    finally:
        import os
        os.unlink(config_path)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
