"""Unit tests for the v4 corpus importer (normalisation / partition / plan /
idempotent execution against the in-memory native store)."""
import json

from cui.research_universe.application import Slice1Service
from cui.research_universe.store.event_store import InMemoryNativeEventStore
from cui.tools import v4_importer as imp
from cui.tools.v4_importer import ACTIVE_WS_COMMAND, Entry


# --- normalisation ---------------------------------------------------------


def test_normalize_arxiv_versions_and_case():
    assert imp.normalize("2312.10793v3") == "arxiv:2312.10793"
    assert imp.normalize("arXiv:1706.03762") == "arxiv:1706.03762"
    assert imp.normalize("0810.1327V1") == "arxiv:0810.1327"
    assert imp.normalize("0411046v2") == "arxiv:0411046"  # old-style 7-digit
    assert imp.normalize("2403.17919") == "arxiv:2403.17919"


def test_normalize_doi_and_local():
    assert imp.normalize("10.1007/S00248-023-02190-1") == "doi:10.1007/s00248-023-02190-1"
    assert imp.normalize("10.1007_s00248-023-02190-1") == "doi:10.1007/s00248-023-02190-1"
    assert imp.normalize("local:30d1cc5d6c90") == "local:30d1cc5d6c90"
    assert imp.normalize("doi: 10.1371/journal.pone.0157111 e0157111") is None  # junk row
    assert imp.normalize("") is None
    assert imp.normalize("not-an-id") is None


def test_partition_boundary():
    assert imp.partition("arxiv:2301.00001") == "active"
    assert imp.partition("arxiv:2212.99999") == "legacy"
    assert imp.partition("arxiv:0411046") == "legacy"
    assert imp.partition("doi:10.1007/x") == "legacy"
    assert imp.partition("local:abc123") == "legacy"


def test_first_title_from_markdown_heading():
    md = "# Attention Is All You Need\n\nsome text\n"
    assert imp.first_title(md) == "Attention Is All You Need"


def test_sanitize_text_strips_control_chars_keeps_newlines():
    dirty = "line one\x00\x01\x02\x1ftwo\n\tthree\rfour"
    assert imp.sanitize_text(dirty) == "line onetwo\n\tthree\rfour"


# --- plan merging (tmp dirs) ------------------------------------------------


def test_build_plan_merges_db_and_json(tmp_path):
    lit = tmp_path / "lit"
    (lit / "cache").mkdir(parents=True)
    parsed = lit / "cache" / "parsed"
    parsed.mkdir()
    import sqlite3
    con = sqlite3.connect(lit / "cache" / "litscribe.db")
    con.execute("CREATE TABLE parsed_docs (paper_id TEXT PRIMARY KEY, markdown TEXT)")
    con.execute("INSERT INTO parsed_docs VALUES (?, ?)", ("2312.10793v3", "# In DB paper\n\nbody"))
    con.commit()
    con.close()
    (parsed / "1706.03762_ab12cd34ef56ab78.json").write_text(json.dumps({"markdown": "# Json only paper\n\nbody"}), encoding="utf-8")
    entries, notes = imp.build_plan(lit)
    keys = {e.key for e in entries}
    assert keys == {"arxiv:2312.10793", "arxiv:1706.03762"}
    assert any("json-union-only" in n for n in notes)
    by_key = {e.key: e for e in entries}
    assert by_key["arxiv:2312.10793"].group == "active"
    assert by_key["arxiv:1706.03762"].group == "legacy"


# --- idempotent execution ---------------------------------------------------


def _store_and_service():
    store = InMemoryNativeEventStore()
    universe = store.create_active_universe("library-a")
    service = Slice1Service(store, actor_id="v4-importer", generator=_Unused())
    return store, universe, service


class _Unused:
    def generate(self, **_): raise AssertionError("must not be used")
    def generate_additional(self, **_): raise AssertionError("must not be used")


def test_execute_plan_is_idempotent_and_deterministic(tmp_path):
    store, universe, service = _store_and_service()
    entries = [
        Entry(key="arxiv:2402.11651", source_id="2402.11651v2", text="# Active one\n\nbody", title="Active one", group="active"),
        Entry(key="doi:10.1007/s00248-023-02190-1", source_id="10.1007/s00248-023-02190-1", text="# Legacy one\n\nbody", title="Legacy one", group="legacy"),
    ]
    first = imp.execute_plan(service, store, universe, entries, tmp_path, write_files=True)
    second = imp.execute_plan(service, store, universe, entries, tmp_path, write_files=True)
    assert first["created"] == 2 and first["replayed"] == 0 and not first["failed"]
    assert second["created"] == 0 and second["replayed"] == 2 and not second["failed"]
    # corpus workspaces exist exactly once each
    ws_active = imp.workspace_id_for(ACTIVE_WS_COMMAND)
    materials = [e.validated_payload() for e in store.read_events(universe) if e.event_type == "material_added"]
    assert len(materials) == 2
    assert all(m.workspace_id == (ws_active if m.source_locator.startswith("arxiv:") else imp.workspace_id_for(imp.LEGACY_WS_COMMAND)) for m in materials)
    # text files written outside the repo
    files = sorted(p.name for p in (tmp_path / "materials").glob("*.md"))
    assert files == ["arxiv_2402.11651.md", "doi_10.1007_s00248-023-02190-1.md"]
