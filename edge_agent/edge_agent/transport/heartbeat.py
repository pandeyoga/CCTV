"""Periodic device heartbeat: POST /api/v1/devices/heartbeat with the current health snapshot.

Independent of visitor events, so a healthy device in an empty store stays visibly connected.
Only the *latest* state is ever sent (no queue): a heartbeat that fails is simply superseded by the
next one, so nothing accumulates while offline. Interval / stale threshold: docs/CONTRACTS.md.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Callable

import httpx

from .. import __version__
from ..contracts import HeartbeatAckV1, HeartbeatV1
from ..health import HealthState, HealthStatus
from .backoff import Backoff
from .sender import interruptible_wait

log = logging.getLogger(__name__)

HEARTBEAT_PATH = "/api/v1/devices/heartbeat"
DEFAULT_INTERVAL_S = 60.0


class HeartbeatSender:
    def __init__(self, health: HealthState, backend_url: str, api_key: str, interval_s: float = DEFAULT_INTERVAL_S,
                 client: httpx.Client | None = None, timeout_s: float = 10.0, max_backoff_s: float = 300.0,
                 sleep: Callable[[float], None] = time.sleep,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        if not api_key:
            raise ValueError("api key is required (EDGE_API_KEY)")
        if interval_s <= 0:
            raise ValueError("interval_s must be > 0")
        self.health = health
        self.interval_s = interval_s
        self._client = client or httpx.Client(timeout=timeout_s)
        self._url = backend_url.rstrip("/") + HEARTBEAT_PATH
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self._bo = Backoff(interval_s, max(max_backoff_s, interval_s))
        self._sleep = sleep
        self._now = now
        self.sent = 0
        self.failed = 0

    def build(self) -> HeartbeatV1:
        snap = self.health.snapshot()
        return HeartbeatV1(
            sent_at=self._now(),
            source_status="ok" if snap.source_status != HealthStatus.SOURCE_DOWN.value else "source_down",
            last_frame_age_s=self.health.last_frame_age_s(self._now()),
            pending_events=snap.buffer_pending, frames_processed=snap.frames_processed,
            tracking_session_id=self.health.tracking_session_id, agent_version=__version__,
        )

    def send_once(self) -> float:
        """Send the current state; returns the delay before the next attempt."""
        body = self.build().model_dump(mode="json")
        try:
            resp = self._client.post(self._url, json=body, headers=self._headers)
            if resp.status_code == 200:
                HeartbeatAckV1.model_validate(resp.json())
                self.sent += 1
                self._bo.reset()
                return self.interval_s
            err = f"heartbeat HTTP {resp.status_code}"
        except httpx.HTTPError as exc:
            err = f"heartbeat network: {type(exc).__name__}"
        except Exception as exc:  # malformed ack
            err = f"heartbeat malformed ack: {type(exc).__name__}"
        self.failed += 1
        delay = self._bo.next_delay()
        log.warning("%s; next heartbeat in %.0fs", err, delay)
        return delay

    def run_forever(self, stop: Callable[[], bool]) -> None:
        while not stop():
            interruptible_wait(self.send_once(), stop, self._sleep)

    def close(self) -> None:
        self._client.close()
