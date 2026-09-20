"""SQLite write-ahead buffer for count events.

Invariants:
- append() commits BEFORE any network attempt; event_id is the primary key and never changes.
- Rows leave 'pending' only via mark_sent() (server ack) or mark_rejected() (server said invalid).
- Capacity applies to pending rows; when full, append() raises BufferFullError. Nothing is dropped silently.
"""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence
from uuid import UUID

from ..contracts import CountEventV1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  event_id   TEXT PRIMARY KEY,
  payload    TEXT NOT NULL,
  status     TEXT NOT NULL CHECK (status IN ('pending','sent','rejected')),
  attempts   INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  sent_at    TEXT,
  last_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_status_created ON events(status, created_at);
"""


class BufferFullError(RuntimeError):
    def __init__(self, capacity: int) -> None:
        super().__init__(f"event buffer full (capacity={capacity}); backend unreachable too long")
        self.capacity = capacity


@dataclass(frozen=True)
class StoreCounts:
    pending: int
    sent: int
    rejected: int


@dataclass(frozen=True)
class PendingRow:
    event: CountEventV1
    attempts: int


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventStore:
    def __init__(self, path: str | Path, capacity: int = 50_000) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.path = str(path)
        self.capacity = capacity
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def append(self, event: CountEventV1) -> None:
        with self._lock:
            pending = self._count("pending")
            if pending >= self.capacity:
                raise BufferFullError(self.capacity)
            self._conn.execute(
                "INSERT INTO events(event_id, payload, status, created_at) VALUES (?, ?, 'pending', ?)",
                (str(event.event_id), event.model_dump_json(), _now_iso()),
            )

    def pending(self, limit: int) -> list[PendingRow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload, attempts FROM events WHERE status='pending' ORDER BY created_at, rowid LIMIT ?",
                (limit,),
            ).fetchall()
        return [PendingRow(CountEventV1.model_validate_json(p), a) for p, a in rows]

    def record_attempt(self, event_ids: Iterable[UUID], error: str | None) -> None:
        ids = [str(i) for i in event_ids]
        if not ids:
            return
        with self._lock:
            self._conn.executemany(
                "UPDATE events SET attempts = attempts + 1, last_error = ? WHERE event_id = ? AND status='pending'",
                [(error, i) for i in ids],
            )

    def mark_sent(self, event_ids: Iterable[UUID]) -> int:
        ids = [str(i) for i in event_ids]
        if not ids:
            return 0
        now = _now_iso()
        with self._lock:
            cur = self._conn.executemany(
                "UPDATE events SET status='sent', sent_at=?, last_error=NULL WHERE event_id=? AND status='pending'",
                [(now, i) for i in ids],
            )
            return cur.rowcount

    def mark_rejected(self, event_id: UUID, reason: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE events SET status='rejected', last_error=? WHERE event_id=? AND status='pending'",
                (reason, str(event_id)),
            )

    def purge_sent(self, keep_last: int = 1000) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM events WHERE status='sent' AND rowid NOT IN "
                "(SELECT rowid FROM events WHERE status='sent' ORDER BY sent_at DESC LIMIT ?)",
                (keep_last,),
            )
            return cur.rowcount

    def counts(self) -> StoreCounts:
        with self._lock:
            return StoreCounts(self._count("pending"), self._count("sent"), self._count("rejected"))

    def status_of(self, event_id: UUID) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT status FROM events WHERE event_id=?", (str(event_id),)).fetchone()
        return row[0] if row else None

    def _count(self, status: str) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM events WHERE status=?", (status,)).fetchone()[0])
