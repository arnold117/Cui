"""Command execution guards that serialize preflight, external generation, and append."""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import threading
from typing import Iterator, Protocol

class CommandExecution(Protocol):
    @contextmanager
    def command_execution(self, universe_id: str, command_id: str) -> Iterator[None]: ...

def command_lock_key(universe_id: str, command_id: str) -> int:
    """Stable signed bigint for PostgreSQL advisory locks."""
    return int.from_bytes(hashlib.sha256(f"ru-generation:{universe_id}:{command_id}".encode()).digest()[:8], "big", signed=True)

class CommandExecutionGuard:
    """In-memory keyed guard. Global order: guard -> append command -> stream -> fence."""
    def __init__(self) -> None:
        self._master=threading.Lock(); self._locks: dict[tuple[str,str], threading.Lock]={}
    @contextmanager
    def command_execution(self, universe_id: str, command_id: str) -> Iterator[None]:
        key=(universe_id,command_id)
        with self._master: lock=self._locks.setdefault(key, threading.Lock())
        lock.acquire()
        try: yield
        finally: lock.release()
