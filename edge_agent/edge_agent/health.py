"""Explicit operational status. Buffer-full and auth failures must be loud, never silent."""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class HealthStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    SOURCE_DOWN = "source_down"
    AUTH_FAILED = "auth_failed"
    BUFFER_FULL = "buffer_full"


_SEVERITY = {HealthStatus.OK: 0, HealthStatus.DEGRADED: 1, HealthStatus.SOURCE_DOWN: 2,
             HealthStatus.AUTH_FAILED: 3, HealthStatus.BUFFER_FULL: 4}


@dataclass
class HealthSnapshot:
    status: str
    transport_status: str
    transport_error: str | None
    source_status: str
    buffer_pending: int
    buffer_capacity: int
    buffer_rejected: int
    events_lost_buffer_full: int
    frames_processed: int
    enter_count: int
    exit_count: int
    updated_at: str


@dataclass
class HealthState:
    buffer_capacity: int = 0
    transport_status: HealthStatus = HealthStatus.OK
    transport_error: str | None = None
    source_status: HealthStatus = HealthStatus.OK
    buffer_pending: int = 0
    buffer_rejected: int = 0
    events_lost_buffer_full: int = 0
    frames_processed: int = 0
    enter_count: int = 0
    exit_count: int = 0
    tracking_session_id: int = 0
    last_frame_at: datetime | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def set_transport(self, status: HealthStatus, error: str | None) -> None:
        with self._lock:
            self.transport_status, self.transport_error = status, error

    def set_source(self, up: bool) -> None:
        with self._lock:
            self.source_status = HealthStatus.OK if up else HealthStatus.SOURCE_DOWN

    def mark_frame(self, ts: datetime) -> None:
        with self._lock:
            self.last_frame_at = ts

    def last_frame_age_s(self, now: datetime | None = None) -> float | None:
        if self.last_frame_at is None:
            return None
        return max(0.0, ((now or datetime.now(timezone.utc)) - self.last_frame_at).total_seconds())

    def overall(self) -> HealthStatus:
        candidates = [self.transport_status, self.source_status]
        if self.buffer_capacity and self.buffer_pending >= self.buffer_capacity:
            candidates.append(HealthStatus.BUFFER_FULL)
        if self.events_lost_buffer_full > 0:
            candidates.append(HealthStatus.BUFFER_FULL)
        return max(candidates, key=lambda s: _SEVERITY[s])

    def snapshot(self) -> HealthSnapshot:
        with self._lock:
            return HealthSnapshot(
                status=self.overall().value,
                transport_status=self.transport_status.value,
                transport_error=self.transport_error,
                source_status=self.source_status.value,
                buffer_pending=self.buffer_pending,
                buffer_capacity=self.buffer_capacity,
                buffer_rejected=self.buffer_rejected,
                events_lost_buffer_full=self.events_lost_buffer_full,
                frames_processed=self.frames_processed,
                enter_count=self.enter_count,
                exit_count=self.exit_count,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )

    def write(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self.snapshot()), indent=2))
