"""v4 corpus importer — migrate LitScribe's parsed corpus into native Cui.

Zero new features (slice0): it replays existing native commands
(create_workspace / add_material) through Slice1Service, so the event store's
command fingerprinting gives rerun idempotency for free: the same deterministic
command_id (``v4-import:<anchor>``) replays to the prior commit on a second run.

Sources (all read-only):
  - ``cache/litscribe.db``  parsed_docs (full markdown per paper)
  - ``cache/parsed/*.json`` union extras (16 entries absent from the DB)
  - ``data/pdfs/``           verification only: every PDF already maps to a DB row

Anchors are normalised ids: ``arxiv:<id>`` (version stripped), ``doi:<doi>``
(lowercased, canonical slashes), ``local:<hash>``. Partition: arXiv YYMM >= 2301
-> ``active`` workspace (LLM-era corpus), everything else -> ``legacy``
workspace (bio-process / old arXiv). Both corpora land as two workspaces in the
library's single active universe.

CLI (backend/)::

    python -m cui.tools.v4_importer --mode dry-run    # default: nothing written
    python -m cui.tools.v4_importer --mode real       # commits + writes files

Human gate: run dry-run first and review the report before ``--mode real``.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from cui.research_universe.application import Slice1Service
from cui.research_universe.store.event_store import NativeEventStore

DEFAULT_LITSCRIBE = Path("/Users/arnold/Documents/Dev/LitScribe")
DEFAULT_DATA_ROOT = Path.home() / ".cui"

ACTIVE_WS_COMMAND = "v4-corpus-active"
LEGACY_WS_COMMAND = "v4-corpus-legacy"
WS_QUESTIONS = {
    ACTIVE_WS_COMMAND: "语料库·active — v4 迁移 LLM 时代 arXiv 群(2026-09-02 importer)",
    LEGACY_WS_COMMAND: "语料库·legacy — v4 迁移生物工艺/DOI/老 arXiv 群(2026-09-02 importer)",
}

_ARXIV = re.compile(r"^(arxiv:)?(\d{4}\.\d{4,5}|0\d{6}|[1-9]\d{5})(v\d+)?$", re.I)
_DOI = re.compile(r"^(?:doi:\s*)?(10\.[^\s]+)$", re.I)
_LOCAL = re.compile(r"^local:\s*([0-9a-f]+)$", re.I)


@dataclass(frozen=True)
class Entry:
    key: str            # canonical anchor: arxiv:<id> / doi:<doi> / local:<hash>
    source_id: str      # original paper_id / json file stem
    text: str
    title: str
    group: str          # "active" | "legacy"


def normalize(paper_id: str) -> str | None:
    """Return the canonical anchor for a v4 paper_id, or None if unusable."""
    pid = (paper_id or "").strip()
    if not pid:
        return None
    m = _DOI.match(pid)
    if m:
        return "doi:" + m.group(1).lower().replace("_", "/").rstrip(".")
    m = _LOCAL.match(pid)
    if m:
        return "local:" + m.group(1).lower()
    m = _ARXIV.match(pid)
    if m:
        body = (m.group(2) or "").lower()
        return "arxiv:" + body
    return None


def partition(key: str) -> str:
    if key.startswith("arxiv:"):
        m = re.match(r"arxiv:(\d{2})(\d{2})", key)
        if m and int(m.group(1) + m.group(2)) >= 2301:
            return "active"
    return "legacy"


def first_title(markdown: str) -> str:
    for line in (markdown or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        return stripped[:120]
    return "(untitled)"


def load_db_rows(db_path: Path) -> dict[str, tuple[str, str]]:
    """key -> (source paper_id, markdown) from parsed_docs."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT paper_id, markdown FROM parsed_docs").fetchall()
    finally:
        con.close()
    return {key: (pid, md or "") for pid, md in rows if (key := normalize(pid))}


def load_json_extras(parsed_dir: Path) -> dict[str, tuple[str, str]]:
    """key -> (json file stem, markdown) for cache/parsed/*.json entries."""
    out: dict[str, tuple[str, str]] = {}
    for path in sorted(parsed_dir.glob("*.json")):
        stem = re.sub(r"_[0-9a-f]{16}$", "", path.stem)
        key = normalize(stem)
        if key is None:
            continue
        try:
            with path.open(encoding="utf-8", errors="replace") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        text = data.get("markdown") if isinstance(data, dict) else None
        if isinstance(text, str) and text.strip():
            out[key] = (stem, text)
    return out


def build_plan(lit_dir: Path) -> tuple[list[Entry], list[str]]:
    """Merge DB + JSON sources into the ordered plan (active first).

    Entries whose text is empty are skipped (a native material requires a
    non-empty excerpt) and reported in the notes.
    """
    db = load_db_rows(lit_dir / "cache" / "litscribe.db")
    extras = load_json_extras(lit_dir / "cache" / "parsed")
    merged: dict[str, tuple[str, str]] = dict(db)
    json_only = []
    for key, (stem, text) in extras.items():
        if key not in merged:
            merged[key] = (f"json:{stem}", text)
            json_only.append(key)
    entries = []
    skipped_empty: list[str] = []
    for key in sorted(merged):
        source_id, text = merged[key]
        if not (text or "").strip():
            skipped_empty.append(key)
            continue
        entries.append(Entry(key=key, source_id=source_id, text=text, title=first_title(text), group=partition(key)))
    entries.sort(key=lambda e: (e.group != "active", e.key))
    notes = [f"json-union-only entries: {len(json_only)} ({', '.join(sorted(json_only)[:6])}...)"] if json_only else []
    if skipped_empty:
        notes.append(f"skipped empty-text entries: {len(skipped_empty)} ({', '.join(skipped_empty[:8])}...)")
    return entries, notes


def workspace_id_for(command_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"slice1:workspace:{command_id}"))


def command_ids_for(entries: list[Entry]) -> dict[str, str]:
    return {e.key: f"v4-import:{e.key}" for e in entries}


def _unavailable(*_args, **_kwargs):
    raise RuntimeError("v4 importer never drives LLM generators")


def ensure_corpus_workspaces(service: Slice1Service, store: NativeEventStore, universe_id: str) -> dict[str, str]:
    """Create (or replay) the active/legacy corpus workspaces; returns id per command."""
    result = {}
    for command_id in (ACTIVE_WS_COMMAND, LEGACY_WS_COMMAND):
        wid = workspace_id_for(command_id)
        committed = service.create_workspace(
            universe_id, command_id, expected_sequence=0, question=WS_QUESTIONS[command_id]
        )
        result[command_id] = committed.result_payload["workspace_id"]
        assert result[command_id] == wid
    return result


def execute_plan(service: Slice1Service, store: NativeEventStore, universe_id: str, entries: list[Entry], data_root: Path, *, write_files: bool) -> dict:
    """Replay add_material for every entry; returns statistics."""
    workspaces = ensure_corpus_workspaces(service, store, universe_id)
    ws_by_group = {"active": workspaces[ACTIVE_WS_COMMAND], "legacy": workspaces[LEGACY_WS_COMMAND]}
    command_ids = command_ids_for(entries)
    stats = {"planned": len(entries), "created": 0, "replayed": 0, "failed": []}
    material_dir = data_root / "materials"
    for entry in entries:
        workspace_id = ws_by_group[entry.group]
        command_id = command_ids[entry.key]
        try:
            result = service.add_material(
                universe_id, workspace_id, excerpt=entry.text, source_locator=entry.key,
                parse_status="parsed", purpose="evidence", command_id=command_id, expected_sequence=0,
            )
        except Exception as exc:  # keep going: report per-item failures
            stats["failed"].append((entry.key, f"{type(exc).__name__}: {exc}"))
            continue
        if getattr(result, "replayed", False):
            stats["replayed"] += 1
        else:
            stats["created"] += 1
        if write_files:
            material_dir.mkdir(parents=True, exist_ok=True)
            safe = entry.key.replace("/", "_").replace(":", "_")
            (material_dir / f"{safe}.md").write_text(entry.text, encoding="utf-8")
    return stats
