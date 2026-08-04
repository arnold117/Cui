"""Native append-only event-store contracts and adapters."""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from sqlalchemy import Engine, and_, insert, select, text, update
from sqlalchemy.exc import IntegrityError

from anneal.research_universe.domain.events import NativeEvent, PendingNativeEvent
from anneal.research_universe.store import schema


class ExpectedSequenceConflict(Exception): pass
class CommandFingerprintConflict(Exception): pass
class UniverseNotFound(Exception): pass
class UniverseAlreadyActive(Exception): pass


@dataclass(frozen=True)
class CommitResult:
    commit_position: int
    event_ids: list[str]
    result_payload: dict[str, object]
    replayed: bool = False


def command_fingerprint(universe_id: str, command_type: str, payload: dict[str, object], targets: list[tuple[str, str, int]]) -> str:
    """Stable fingerprint includes command semantics, canonical JSON, target and expectation."""
    canonical = json.dumps(
        {"universe_id": universe_id, "command_type": command_type, "payload": payload, "targets": sorted(targets)},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class NativeEventStore(Protocol):
    def create_active_universe(self, library_id: str, universe_id: str | None = None) -> str: ...
    def get_active_universe(self, library_id: str) -> str | None: ...
    def append(self, *, universe_id: str, command_id: str, command_type: str, command_payload: dict[str, object], actor_kind: str, actor_id: str | None, expected_sequences: dict[tuple[str, str], int], events: list[PendingNativeEvent], result_payload: dict[str, object]) -> CommitResult: ...
    def read_events(self, universe_id: str) -> list[NativeEvent]: ...


class InMemoryNativeEventStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._universes: dict[str, tuple[str, datetime, datetime | None]] = {}
        self._streams: dict[tuple[str, str, str], tuple[str, int]] = {}
        self._commands: dict[tuple[str, str], tuple[str, CommitResult]] = {}
        self._events: list[NativeEvent] = []
        self._position = 0

    def create_active_universe(self, library_id: str, universe_id: str | None = None) -> str:
        with self._lock:
            if self.get_active_universe(library_id):
                raise UniverseAlreadyActive(library_id)
            universe_id = universe_id or str(uuid4())
            self._universes[universe_id] = (library_id, datetime.now(timezone.utc), None)
            return universe_id

    def get_active_universe(self, library_id: str) -> str | None:
        return next((uid for uid, (lid, _, archived) in self._universes.items() if lid == library_id and archived is None), None)

    def append(self, **kwargs: object) -> CommitResult:
        universe_id = kwargs["universe_id"]  # type: ignore[assignment]
        command_id = kwargs["command_id"]  # type: ignore[assignment]
        command_type = kwargs["command_type"]  # type: ignore[assignment]
        command_payload = kwargs["command_payload"]  # type: ignore[assignment]
        expected_sequences = kwargs["expected_sequences"]  # type: ignore[assignment]
        pending_events = kwargs["events"]  # type: ignore[assignment]
        result_payload = kwargs["result_payload"]  # type: ignore[assignment]
        actor_kind = kwargs["actor_kind"]  # type: ignore[assignment]
        actor_id = kwargs["actor_id"]  # type: ignore[assignment]
        targets = [(kind, ident, expected) for (kind, ident), expected in expected_sequences.items()]
        fingerprint = command_fingerprint(str(universe_id), command_type, command_payload, targets)
        with self._lock:
            if universe_id not in self._universes: raise UniverseNotFound(str(universe_id))
            prior = self._commands.get((str(universe_id), str(command_id)))
            if prior:
                if prior[0] != fingerprint: raise CommandFingerprintConflict(str(command_id))
                return CommitResult(**{**prior[1].__dict__, "replayed": True})
            addresses = sorted({(str(universe_id), event.aggregate_type, event.aggregate_id) for event in pending_events})
            if set((kind, ident) for _, kind, ident in addresses) != set(expected_sequences):
                raise ValueError("expected sequences must cover precisely every target stream")
            for address in addresses:
                next_sequence = self._streams.get(address, ("", 0))[1]
                if next_sequence != expected_sequences[(address[1], address[2])]: raise ExpectedSequenceConflict(str(address))
            self._position += 1
            position = self._position
            streams = {address: self._streams.setdefault(address, (str(uuid4()), 0))[0] for address in addresses}
            created: list[NativeEvent] = []
            for index, pending in enumerate(pending_events):
                pending.validated_payload()
                address = (str(universe_id), pending.aggregate_type, pending.aggregate_id)
                stream_id, next_sequence = self._streams[address]
                event = NativeEvent(universe_id=str(universe_id), aggregate_type=pending.aggregate_type, aggregate_id=pending.aggregate_id, stream_id=stream_id, sequence=next_sequence, commit_position=position, commit_index=index, event_type=pending.event_type, actor_kind=str(actor_kind), actor_id=actor_id if isinstance(actor_id, str) else None, payload=pending.validated_payload().model_dump(mode="json"), causation_id=pending.causation_id, correlation_id=pending.correlation_id, schema_version=pending.schema_version)
                created.append(event); self._streams[address] = (stream_id, next_sequence + 1)
            self._events.extend(created)
            result = CommitResult(position, [e.id for e in created], result_payload)  # type: ignore[arg-type]
            self._commands[(str(universe_id), str(command_id))] = (fingerprint, result)
            return result

    def read_events(self, universe_id: str) -> list[NativeEvent]:
        with self._lock:
            return sorted((event for event in self._events if event.universe_id == universe_id), key=lambda e: (e.commit_position, e.commit_index))


class PostgresNativeEventStore:
    """Postgres adapter. Locks streams in canonical order inside one transaction."""
    def __init__(self, engine: Engine) -> None: self._engine = engine

    def create_active_universe(self, library_id: str, universe_id: str | None = None) -> str:
        universe_id = universe_id or str(uuid4())
        try:
            with self._engine.begin() as conn:
                conn.execute(insert(schema.research_universes).values(id=universe_id, library_id=library_id, model_generation="research_universe_v1", created_at=datetime.now(timezone.utc)))
        except IntegrityError as exc: raise UniverseAlreadyActive(library_id) from exc
        return universe_id

    def get_active_universe(self, library_id: str) -> str | None:
        with self._engine.connect() as conn:
            return conn.execute(select(schema.research_universes.c.id).where(schema.research_universes.c.library_id == library_id, schema.research_universes.c.archived_at.is_(None))).scalar_one_or_none()

    def append(self, *, universe_id: str, command_id: str, command_type: str, command_payload: dict[str, object], actor_kind: str, actor_id: str | None, expected_sequences: dict[tuple[str, str], int], events: list[PendingNativeEvent], result_payload: dict[str, object]) -> CommitResult:
        targets = [(kind, ident, expected) for (kind, ident), expected in expected_sequences.items()]
        fingerprint = command_fingerprint(str(universe_id), command_type, command_payload, targets)
        addresses = sorted({(event.aggregate_type, event.aggregate_id) for event in events})
        if set(addresses) != set(expected_sequences): raise ValueError("expected sequences must cover precisely every target stream")
        for event in events: event.validated_payload()
        with self._engine.begin() as conn:
            # Serialize commit-position allocation across every universe.  The row is
            # locked until transaction commit, so a later committed command can never
            # acquire a lower replay cursor position.
            fence_rows = conn.execute(select(schema.ru_commit_fence.c.id).with_for_update()).scalars().all()
            if fence_rows != [1]:
                raise RuntimeError("native commit fence is missing or corrupt; run alembic upgrade head")
            # Same command retries serialize before rechecking their durable commit.
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"ru-command:{universe_id}:{command_id}"})
            existing = conn.execute(select(schema.ru_commits).where(schema.ru_commits.c.command_id == command_id, schema.ru_commits.c.universe_id == universe_id).with_for_update()).mappings().one_or_none()
            if existing:
                if existing["command_fingerprint"] != fingerprint: raise CommandFingerprintConflict(command_id)
                ids = conn.execute(select(schema.ru_events.c.id).where(schema.ru_events.c.commit_position == existing["position"]).order_by(schema.ru_events.c.commit_index)).scalars().all()
                return CommitResult(existing["position"], list(ids), existing["result_payload"], True)
            universe_row = conn.execute(select(schema.research_universes.c.id).where(schema.research_universes.c.id == universe_id).with_for_update()).scalar_one_or_none()
            if universe_row is None: raise UniverseNotFound(universe_id)
            streams: dict[tuple[str, str], tuple[str, int]] = {}
            for aggregate_type, aggregate_id in addresses:
                # Covers absent streams too; advisory lock is released with this tx.
                conn.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"ru-stream:{universe_id}:{aggregate_type}:{aggregate_id}"})
                row = conn.execute(select(schema.ru_streams).where(schema.ru_streams.c.universe_id == universe_id, schema.ru_streams.c.aggregate_type == aggregate_type, schema.ru_streams.c.aggregate_id == aggregate_id).with_for_update()).mappings().one_or_none()
                actual = row["next_sequence"] if row else 0
                if actual != expected_sequences[(aggregate_type, aggregate_id)]: raise ExpectedSequenceConflict(f"{aggregate_type}/{aggregate_id}")
                stream_id = row["id"] if row else str(uuid4())
                streams[(aggregate_type, aggregate_id)] = (stream_id, actual)
            commit_id = str(uuid4())
            position = conn.execute(insert(schema.ru_commits).values(id=commit_id, universe_id=universe_id, command_id=command_id, command_fingerprint=fingerprint, result_payload=result_payload, actor_kind=actor_kind, actor_id=actor_id, committed_at=datetime.now(timezone.utc)).returning(schema.ru_commits.c.position)).scalar_one()
            for address, (stream_id, next_sequence) in streams.items():
                row = conn.execute(select(schema.ru_streams.c.id).where(schema.ru_streams.c.id == stream_id)).scalar_one_or_none()
                if row is None: conn.execute(insert(schema.ru_streams).values(id=stream_id, universe_id=universe_id, aggregate_type=address[0], aggregate_id=address[1], next_sequence=next_sequence, created_at=datetime.now(timezone.utc)))
            ids = []
            for index, pending in enumerate(events):
                address = (pending.aggregate_type, pending.aggregate_id); stream_id, sequence = streams[address]; event_id = str(uuid4()); ids.append(event_id)
                conn.execute(insert(schema.ru_events).values(id=event_id, universe_id=universe_id, stream_id=stream_id, commit_position=position, commit_index=index, sequence=sequence, event_type=pending.event_type, occurred_at=datetime.now(timezone.utc), payload=pending.validated_payload().model_dump(mode="json"), causation_id=pending.causation_id, correlation_id=pending.correlation_id, schema_version=pending.schema_version))
                streams[address] = (stream_id, sequence + 1)
            for address, (stream_id, next_sequence) in streams.items(): conn.execute(update(schema.ru_streams).where(schema.ru_streams.c.id == stream_id).values(next_sequence=next_sequence))
            return CommitResult(position, ids, result_payload)

    def read_events(self, universe_id: str) -> list[NativeEvent]:
        with self._engine.connect() as conn:
            rows = conn.execute(select(schema.ru_events, schema.ru_streams.c.aggregate_type, schema.ru_streams.c.aggregate_id, schema.ru_commits.c.actor_kind, schema.ru_commits.c.actor_id).join(schema.ru_streams, schema.ru_events.c.stream_id == schema.ru_streams.c.id).join(schema.ru_commits, and_(schema.ru_events.c.commit_position == schema.ru_commits.c.position, schema.ru_events.c.universe_id == schema.ru_commits.c.universe_id)).where(schema.ru_events.c.universe_id == universe_id).order_by(schema.ru_events.c.commit_position, schema.ru_events.c.commit_index)).mappings()
            return [NativeEvent(id=row["id"], universe_id=row["universe_id"], aggregate_type=row["aggregate_type"], aggregate_id=row["aggregate_id"], stream_id=row["stream_id"], sequence=row["sequence"], commit_position=row["commit_position"], commit_index=row["commit_index"], event_type=row["event_type"], actor_kind=row["actor_kind"], actor_id=row["actor_id"], occurred_at=row["occurred_at"], payload=row["payload"], causation_id=row["causation_id"], correlation_id=row["correlation_id"], schema_version=row["schema_version"]) for row in rows]
