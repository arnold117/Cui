"""Fail-closed validation against the frozen legacy_baseline migration manifest."""
from __future__ import annotations
import os
from typing import Any
from sqlalchemy import create_engine, inspect

# Immutable schema contract transcribed from 20260804_01_legacy_baseline.py.
# Never derive this from mutable runtime SQLAlchemy metadata.
FROZEN_LEGACY_MANIFEST: dict[str, dict[str, Any]] = {
 "libraries": {"columns": {"id":("text",False,None),"name":("text",False,None),"created_at":("datetime",False,None)},"pk":("id",),"unique":set(),"checks":set(),"fks":set(),"indexes":set()},
 "projects": {"columns": {"id":("text",False,None),"library_id":("text",False,None),"goal":("text",False,None)},"pk":("id",),"unique":set(),"checks":set(),"fks":{(("library_id",),(("libraries","id"),))},"indexes":set()},
 "conversations": {"columns": {"id":("text",False,None),"library_id":("text",False,None),"created_at":("datetime",False,None),"updated_at":("datetime",False,None)},"pk":("id",),"unique":set(),"checks":set(),"fks":{(("library_id",),(("libraries","id"),))},"indexes":set()},
 "claims": {"columns": {"id":("text",False,None),"library_id":("text",False,None),"body":("text",False,None),"created_at":("datetime",False,None),"updated_at":("datetime",False,None)},"pk":("id",),"unique":set(),"checks":set(),"fks":{(("library_id",),(("libraries","id"),))},"indexes":set()},
 "artifacts": {"columns": {"id":("text",False,None),"library_id":("text",False,None),"kind":("text",False,None),"goal":("text",False,None),"constraints":("json",False,"[]"),"title":("text",False,""),"created_at":("datetime",False,None),"updated_at":("datetime",False,None)},"pk":("id",),"unique":set(),"checks":set(),"fks":{(("library_id",),(("libraries","id"),))},"indexes":set()},
 "materials": {"columns": {"id":("text",False,None),"library_id":("text",False,None),"kind":("text",False,None),"provenance":("json",False,"{}"),"payload":("json",False,"{}")},"pk":("id",),"unique":set(),"checks":set(),"fks":{(("library_id",),(("libraries","id"),))},"indexes":set()},
 "conversation_projects": {"columns":{"conversation_id":("text",False,None),"project_id":("text",False,None)},"pk":("conversation_id","project_id"),"unique":set(),"checks":set(),"fks":{(("conversation_id",),(("conversations","id"),)),(("project_id",),(("projects","id"),))},"indexes":set()},
 "claim_artifacts": {"columns":{"claim_id":("text",False,None),"artifact_id":("text",False,None)},"pk":("claim_id","artifact_id"),"unique":set(),"checks":set(),"fks":{(("claim_id",),(("claims","id"),)),(("artifact_id",),(("artifacts","id"),))},"indexes":set()},
 "artifact_projects": {"columns":{"artifact_id":("text",False,None),"project_id":("text",False,None)},"pk":("artifact_id","project_id"),"unique":set(),"checks":set(),"fks":{(("artifact_id",),(("artifacts","id"),)),(("project_id",),(("projects","id"),))},"indexes":set()},
 "artifact_materials": {"columns":{"artifact_id":("text",False,None),"material_id":("text",False,None)},"pk":("artifact_id","material_id"),"unique":set(),"checks":set(),"fks":{(("artifact_id",),(("artifacts","id"),)),(("material_id",),(("materials","id"),))},"indexes":set()},
 "events": {"columns":{"id":("text",False,None),"artifact_id":("text",False,None),"seq":("bigint",False,None),"ts":("datetime",False,None),"type":("text",False,None),"data":("json",False,None)},"pk":("id",),"unique":set(),"checks":set(),"fks":set(),"indexes":{("ix_events_artifact_id",("artifact_id",),False)}},
 "lens_feed_entries": {"columns":{"id":("text",False,None),"library_id":("text",False,None),"artifact_id":("text",False,None),"event_id":("text",False,None),"event_type":("text",False,None),"ingested_at":("datetime",False,None)},"pk":("id",),"unique":set(),"checks":set(),"fks":{(("library_id",),(("libraries","id"),))},"indexes":{("ix_lens_feed_entries_library_id",("library_id",),False)}},
}

def _type_name(type_: Any) -> str:
    raw = type_.__class__.__name__.lower()
    return {"varchar":"text", "string":"text", "datetime":"datetime", "timestamp":"datetime", "jsonb":"json", "json":"json", "biginteger":"bigint", "integer":"integer", "text":"text"}.get(raw, raw)
def _default(value: Any) -> str | None:
    if value is None: return None
    text = str(value).strip()
    while text.startswith("(") and text.endswith(")"): text = text[1:-1].strip()
    text = text.replace("::jsonb", "").replace("::json", "").replace("::text", "").strip()
    if len(text) >= 2 and text[0] == text[-1] == "'": text = text[1:-1]
    return text

def _manifest_from_inspector(inspector: Any) -> dict[str, dict[str, Any]]:
    result = {}
    for name in inspector.get_table_names():
        result[name] = {"columns": {c["name"]: (_type_name(c["type"]), bool(c["nullable"]), _default(c.get("default"))) for c in inspector.get_columns(name)}, "pk": tuple(inspector.get_pk_constraint(name).get("constrained_columns") or ()), "unique": {tuple(x["column_names"]) for x in inspector.get_unique_constraints(name) if x.get("column_names")}, "checks": {str(x["sqltext"]).replace(" ", "") for x in inspector.get_check_constraints(name)}, "fks": {(tuple(x["constrained_columns"]), tuple((x["referred_table"], col) for col in x["referred_columns"])) for x in inspector.get_foreign_keys(name)}, "indexes": {(x.get("name"), tuple(x["column_names"]), bool(x.get("unique"))) for x in inspector.get_indexes(name)}}
    return result

def verify_legacy_schema(database_url: str) -> None:
    engine=create_engine(database_url)
    try: actual=_manifest_from_inspector(inspect(engine))
    finally: engine.dispose()
    if actual != FROZEN_LEGACY_MANIFEST:
        for table in sorted(set(actual)|set(FROZEN_LEGACY_MANIFEST)):
            if actual.get(table) != FROZEN_LEGACY_MANIFEST.get(table): raise RuntimeError(f"legacy schema mismatch in {table}: expected {FROZEN_LEGACY_MANIFEST.get(table)!r}, found {actual.get(table)!r}")
        raise RuntimeError("legacy schema mismatch")
def main() -> None:
    url=os.getenv("ANNEAL_DATABASE_URL")
    if not url: raise RuntimeError("ANNEAL_DATABASE_URL is required")
    verify_legacy_schema(url); print("legacy schema matches frozen baseline; safe to stamp legacy_baseline")
if __name__ == "__main__": main()
