"""Library-scoped sealed PARK storage. Raw captures never enter Research Universe events."""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib, json, threading
from uuid import NAMESPACE_URL, uuid5
import sqlalchemy as sa
from sqlalchemy import Engine, insert, select
from cui.research_universe.store import schema
from cui.research_universe.store.event_store import CommandFingerprintConflict, ExpectedSequenceConflict

@dataclass(frozen=True)
class SealedCapture:
    id: str; library_id: str; original_text: str; created_at: datetime
@dataclass(frozen=True)
class SealedCommit:
    capture_id: str; result_payload: dict[str, object]; replayed: bool = False

def fingerprint(library_id: str, text: str, expected: int) -> str:
    return hashlib.sha256(json.dumps({"library_id":library_id,"original_text":text,"expected_sequence":expected}, sort_keys=True).encode()).hexdigest()

class InMemorySealedParkStore:
    def __init__(self): self._lock=threading.RLock(); self._captures={}; self._commands={}
    def capture(self, library_id, command_id, expected_sequence, original_text):
        fp=fingerprint(library_id, original_text, expected_sequence)
        with self._lock:
            prior=self._commands.get((library_id, command_id))
            if prior:
                if prior[0] != fp: raise CommandFingerprintConflict(command_id)
                return SealedCommit(**{**prior[1].__dict__, "replayed":True})
            if expected_sequence != 0: raise ExpectedSequenceConflict("sealed_park_capture")
            cid=str(uuid5(NAMESPACE_URL, f"sealed-park:{library_id}:{command_id}")); cap=SealedCapture(cid,library_id,original_text,datetime.now(timezone.utc))
            result=SealedCommit(cid,{"capture_id":cid,"aggregate_sequences":{"sealed_park_capture":1}}); self._captures[cid]=cap; self._commands[(library_id,command_id)]=(fp,result); return result
    def get(self, library_id, capture_id):
        cap=self._captures.get(capture_id)
        if cap is None or cap.library_id != library_id: return None
        return cap
    def list(self, library_id): return sorted((x for x in self._captures.values() if x.library_id==library_id), key=lambda x:x.created_at)

class PostgresSealedParkStore:
    def __init__(self, engine: Engine): self._engine=engine
    def capture(self, library_id, command_id, expected_sequence, original_text):
        fp=fingerprint(library_id, original_text, expected_sequence); cid=str(uuid5(NAMESPACE_URL, f"sealed-park:{library_id}:{command_id}"))
        with self._engine.begin() as c:
            prior=c.execute(select(schema.sealed_park_commands).where(schema.sealed_park_commands.c.library_id==library_id, schema.sealed_park_commands.c.command_id==command_id)).mappings().one_or_none()
            if prior:
                if prior["command_fingerprint"] != fp: raise CommandFingerprintConflict(command_id)
                return SealedCommit(prior["capture_id"], prior["result_payload"], True)
            if expected_sequence != 0: raise ExpectedSequenceConflict("sealed_park_capture")
            now=datetime.now(timezone.utc); result={"capture_id":cid,"aggregate_sequences":{"sealed_park_capture":1}}
            c.execute(insert(schema.sealed_park_captures).values(id=cid,library_id=library_id,original_text=original_text,created_at=now))
            c.execute(insert(schema.sealed_park_commands).values(library_id=library_id,command_id=command_id,command_fingerprint=fp,capture_id=cid,result_payload=result,committed_at=now))
            return SealedCommit(cid,result)
    def get(self, library_id, capture_id):
        with self._engine.connect() as c:
            r=c.execute(select(schema.sealed_park_captures).where(schema.sealed_park_captures.c.id==capture_id,schema.sealed_park_captures.c.library_id==library_id)).mappings().one_or_none()
            return SealedCapture(r["id"],r["library_id"],r["original_text"],r["created_at"]) if r else None
    def list(self, library_id):
        with self._engine.connect() as c: return [SealedCapture(r["id"],r["library_id"],r["original_text"],r["created_at"]) for r in c.execute(select(schema.sealed_park_captures).where(schema.sealed_park_captures.c.library_id==library_id).order_by(schema.sealed_park_captures.c.created_at)).mappings()]
