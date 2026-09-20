"""Outbound HTTPS sender: pending SQLite rows -> POST /api/v1/events/batch -> mark sent on ack.

Edge always dials out; nothing listens. Auth: `Authorization: Bearer <device api key>` (never logged).
Retry: exponential backoff with jitter on network errors / 5xx / 429; auth failures surface as AUTH_FAILED.
`max_backoff_s` bounds the final delay including jitter (see transport/backoff.py); the exponent is capped so an
unbounded number of failures can never overflow. Backoff resets after the first acknowledged batch.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable

import httpx

from ..contracts import EventBatchRequestV1, EventBatchResponseV1
from ..health import HealthState, HealthStatus
from ..storage.event_store import EventStore
from .backoff import Backoff

log = logging.getLogger(__name__)

EVENTS_BATCH_PATH = "/api/v1/events/batch"


WAIT_SLICE_S = 0.5


def interruptible_wait(delay_s: float, stop: Callable[[], bool], sleep: Callable[[float], None]) -> None:
    """Sleep `delay_s` in short slices so a shutdown request is honoured within WAIT_SLICE_S."""
    remaining = delay_s
    while remaining > 0 and not stop():
        step = min(WAIT_SLICE_S, remaining)
        sleep(step)
        remaining -= step


class SendOutcome(str, Enum):
    NOTHING_TO_SEND = "nothing_to_send"
    SENT = "sent"
    RETRY = "retry"
    AUTH_FAILED = "auth_failed"
    BAD_REQUEST = "bad_request"


@dataclass(frozen=True)
class SendResult:
    outcome: SendOutcome
    accepted: int = 0
    duplicates: int = 0
    rejected: int = 0
    next_delay_s: float = 0.0
    error: str | None = None


class EventSender:
    def __init__(self, store: EventStore, backend_url: str, api_key: str, health: HealthState,
                 client: httpx.Client | None = None, batch_size: int = 100, timeout_s: float = 10.0,
                 base_backoff_s: float = 1.0, max_backoff_s: float = 60.0,
                 sleep: Callable[[float], None] = time.sleep, rng: Callable[[], float] = random.random) -> None:
        if not api_key:
            raise ValueError("api key is required (EDGE_API_KEY)")
        self.store = store
        self.health = health
        self.batch_size = batch_size
        self.base_backoff_s = base_backoff_s
        self.max_backoff_s = max_backoff_s
        self._sleep = sleep
        self._bo = Backoff(base_backoff_s, max_backoff_s, rng)
        self._client = client or httpx.Client(timeout=timeout_s)
        self._url = backend_url.rstrip("/") + EVENTS_BATCH_PATH
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    @property
    def failures(self) -> int:
        return self._bo.failures

    def _backoff(self) -> float:
        return self._bo.next_delay()

    def send_once(self) -> SendResult:
        rows = self.store.pending(self.batch_size)
        if not rows:
            self.health.set_transport(HealthStatus.OK, None)
            return SendResult(SendOutcome.NOTHING_TO_SEND)

        ids = [r.event.event_id for r in rows]
        body = EventBatchRequestV1(events=[r.event for r in rows]).model_dump(mode="json")
        try:
            resp = self._client.post(self._url, json=body, headers=self._headers)
        except httpx.HTTPError as exc:
            err = f"network: {type(exc).__name__}"
            self.store.record_attempt(ids, err)
            delay = self._backoff()
            self.health.set_transport(HealthStatus.DEGRADED, err)
            log.warning("send failed (%s); retry in %.1fs", err, delay)
            return SendResult(SendOutcome.RETRY, next_delay_s=delay, error=err)

        if resp.status_code in (401, 403):
            err = f"auth rejected (HTTP {resp.status_code})"
            self.store.record_attempt(ids, err)
            delay = self._backoff()
            self.health.set_transport(HealthStatus.AUTH_FAILED, err)
            log.error("%s; check device API key", err)
            return SendResult(SendOutcome.AUTH_FAILED, next_delay_s=delay, error=err)

        if resp.status_code == 429 or resp.status_code >= 500:
            err = f"server HTTP {resp.status_code}"
            self.store.record_attempt(ids, err)
            delay = self._backoff()
            self.health.set_transport(HealthStatus.DEGRADED, err)
            log.warning("%s; retry in %.1fs", err, delay)
            return SendResult(SendOutcome.RETRY, next_delay_s=delay, error=err)

        if resp.status_code >= 400:
            err = f"batch rejected HTTP {resp.status_code}"
            self.store.record_attempt(ids, err)
            delay = self._backoff()
            self.health.set_transport(HealthStatus.DEGRADED, err)
            log.error("%s; body kept pending for inspection", err)
            return SendResult(SendOutcome.BAD_REQUEST, next_delay_s=delay, error=err)

        try:
            ack = EventBatchResponseV1.model_validate(resp.json())
        except Exception as exc:  # malformed ack: do NOT mark sent
            err = f"malformed ack: {type(exc).__name__}"
            self.store.record_attempt(ids, err)
            delay = self._backoff()
            self.health.set_transport(HealthStatus.DEGRADED, err)
            return SendResult(SendOutcome.RETRY, next_delay_s=delay, error=err)

        sent_ids = set(ack.accepted) | set(ack.duplicates)
        self.store.mark_sent([i for i in ids if i in sent_ids])
        for rej in ack.rejected:
            if rej.event_id in ids:
                self.store.mark_rejected(rej.event_id, rej.reason)
        unacked = [i for i in ids if i not in sent_ids and i not in {r.event_id for r in ack.rejected}]
        if unacked:
            self.store.record_attempt(unacked, "not acknowledged by server")
        self._bo.reset()
        self.health.set_transport(HealthStatus.OK, None)
        return SendResult(SendOutcome.SENT, accepted=len(ack.accepted), duplicates=len(ack.duplicates),
                          rejected=len(ack.rejected))

    def flush(self, max_batches: int = 1000) -> list[SendResult]:
        results: list[SendResult] = []
        for _ in range(max_batches):
            r = self.send_once()
            results.append(r)
            if r.outcome is SendOutcome.NOTHING_TO_SEND:
                break
            if r.outcome is not SendOutcome.SENT:
                self._sleep(r.next_delay_s)
        return results

    def run_forever(self, stop: Callable[[], bool], idle_sleep_s: float = 1.0) -> None:
        while not stop():
            r = self.send_once()
            if r.outcome is SendOutcome.SENT:
                continue
            interruptible_wait(r.next_delay_s if r.next_delay_s > 0 else idle_sleep_s, stop, self._sleep)

    def close(self) -> None:
        self._client.close()
