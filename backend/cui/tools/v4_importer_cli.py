"""CLI entry for the v4 corpus importer.

    python -m cui.tools.v4_importer_cli --mode dry-run   # default
    python -m cui.tools.v4_importer_cli --mode real

``real`` commits into the database that ``CUI_DATABASE_URL`` points at
(backend/.env in dev), after asserting the schema is at head — same boot
semantics as ``cui.api.app.create_native_app``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cui.api.app import _assert_database_at_head, _resolve_library_context
from cui.research_universe.application import Slice1Service
from cui.research_universe.store.event_store import PostgresNativeEventStore
from cui.store.database import create_db_engine
from cui.tools import v4_importer
from cui.tools.v4_importer import ACTIVE_WS_COMMAND, LEGACY_WS_COMMAND


def _stub_generator() -> object:
    def _raise(*_args, **_kwargs):
        raise RuntimeError("v4 importer never drives LLM generators")
    return type("UnavailableGenerator", (), {"generate": _raise, "generate_additional": _raise})()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v4 corpus importer (slice0 T5)")
    parser.add_argument("--mode", choices=["dry-run", "real"], default="dry-run")
    parser.add_argument("--lit-dir", type=Path, default=v4_importer.DEFAULT_LITSCRIBE)
    parser.add_argument("--data-root", type=Path, default=v4_importer.DEFAULT_DATA_ROOT)
    parser.add_argument("--limit", type=int, default=0, help="0 = all entries")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv
    load_dotenv()

    entries, notes = v4_importer.build_plan(args.lit_dir)
    if args.limit:
        entries = entries[: args.limit]
    print("=" * 70)
    print(f"v4 corpus plan ({args.mode})")
    print(f"  lit-dir      : {args.lit_dir}")
    print(f"  planned      : {len(entries)}")
    active = sum(1 for e in entries if e.group == "active")
    print(f"  active/legacy: {active} / {len(entries) - active}")
    for note in notes:
        print(f"  note: {note}")
    for entry in entries[:3]:
        print(f"    e.g. {entry.key:<48} group={entry.group} text={len(entry.text)}B")
    if len(entries) > 3:
        print(f"    ... ({len(entries) - 3} more)")

    if args.mode == "dry-run":
        print("dry-run: no database write, no file write. Review, then --mode real.")
        return 0

    import os
    url = os.getenv("CUI_DATABASE_URL")
    if not url:
        print("SETUP ERROR: CUI_DATABASE_URL required for real mode", file=sys.stderr)
        return 2
    _assert_database_at_head(url)
    engine = create_db_engine(url)
    context = _resolve_library_context(engine)
    store = PostgresNativeEventStore(engine)
    universe = store.get_active_universe(context.library_id)
    if universe is None:
        universe = store.create_active_universe(context.library_id)
    service = Slice1Service(store, actor_id="v4-importer", generator=_stub_generator())
    stats = v4_importer.execute_plan(service, store, universe, entries, args.data_root, write_files=True)
    print("-" * 70)
    print(f"commit stats  : created={stats['created']} replayed={stats['replayed']} failed={len(stats['failed'])}")
    print(f"corpus workspaces (in universe {universe}):")
    for cmd in (ACTIVE_WS_COMMAND, LEGACY_WS_COMMAND):
        print(f"  {cmd:<18} -> {v4_importer.workspace_id_for(cmd)}")
    for key, reason in stats["failed"][:10]:
        print(f"  FAILED {key}: {reason}")
    return 0 if not stats["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
