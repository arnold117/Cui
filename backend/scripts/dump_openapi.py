"""Dump the backend OpenAPI schema (single source of truth for frontend types). Run via `make contract`."""
import json
import sys
from pathlib import Path

from cui.api.app import create_native_test_app
from cui.research_universe.api.routes import LibraryContext, LocalPrincipal
from cui.research_universe.api.slice9 import create_dialogue_router
from cui.research_universe.store.event_store import InMemoryNativeEventStore

OUT = Path(__file__).resolve().parents[2] / "frontend/src/features/research-universe/openapi.json"


def build_openapi() -> dict:
    # 无 DB 的测试 app 没挂 dialogue router(它们自己挂),这里补上以得到完整 schema;client=None 不影响 schema。
    store = InMemoryNativeEventStore()
    app = create_native_test_app(store)
    from cui.research_universe.application import Slice1Service
    service = Slice1Service(store, LocalPrincipal().id, None, None)
    app.include_router(create_dialogue_router(service, store, LibraryContext("default"), LocalPrincipal(), None), prefix="/api/v2")
    return app.openapi()


def render() -> str:
    return json.dumps(build_openapi(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


if __name__ == "__main__":
    OUT.write_text(render())
    print(f"wrote {OUT}", file=sys.stderr)
