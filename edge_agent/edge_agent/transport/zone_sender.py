"""Zone sample sender (ADR-031): bounded in-memory queue -> POST /api/v1/zones/samples in batches.

Deliberately NOT durable (unlike count events): samples are telemetry; when the queue is full the oldest are dropped
and `dropped` counts it loudly in the log."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Callable

import httpx

from ..contracts import ZoneSampleBatchRequestV1, ZoneSampleBatchResponseV1, ZoneSampleV1
from .backoff import Backoff
from .sender import interruptible_wait

log = logging.getLogger(__name__)
SAMPLES_PATH = "/api/v1/zones/samples"


class ZoneSampleSender:
    def __init__(self, backend_url: str, api_key: str, batch_size: int = 100, max_queue: int = 5000, interval_s: float = 5.0,
                 client: httpx.Client | None = None, timeout_s: float = 10.0, base_backoff_s: float = 1.0, max_backoff_s: float = 60.0,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if not api_key:
            raise ValueError("api key is required (EDGE_API_KEY)")
        self._q: deque[ZoneSampleV1] = deque(maxlen=max_queue)
        self._lock = threading.Lock()
        self.batch_size = batch_size
        self.interval_s = interval_s
        self._client = client or httpx.Client(timeout=timeout_s)
        self._url = backend_url.rstrip("/") + SAMPLES_PATH
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self._bo = Backoff(base_backoff_s, max_backoff_s)
        self._sleep = sleep
        self.sent = 0
        self.rejected = 0
        self.dropped = 0

    def enqueue(self, samples: list[ZoneSampleV1]) -> None:
        with self._lock:
            for s in samples:
                if len(self._q) == self._q.maxlen:
                    self.dropped += 1
                    if self.dropped in (1, 100, 1000) or self.dropped % 10000 == 0:
                        log.error("zone sample queue full: %d samples dropped so far", self.dropped)
                self._q.append(s)

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._q)

    def send_once(self) -> float:
        with self._lock:
            batch = list(self._q)[: self.batch_size]
        if not batch:
            return self.interval_s
        body = ZoneSampleBatchRequestV1(samples=batch).model_dump(mode="json")
        try:
            resp = self._client.post(self._url, json=body, headers=self._headers)
            if resp.status_code == 200:
                ack = ZoneSampleBatchResponseV1.model_validate(resp.json())
                done = set(ack.accepted) | set(ack.duplicates) | {r.sample_id for r in ack.rejected}
                self.rejected += len(ack.rejected)
                with self._lock:
                    for _ in range(len(batch)):  # batch == queue head; drop exactly the acknowledged ones
                        if self._q and self._q[0].sample_id in done:
                            self._q.popleft()
                        else:
                            break
                self.sent += len(ack.accepted) + len(ack.duplicates)
                self._bo.reset()
                return 0.0 if self.pending else self.interval_s
            err = f"zone samples HTTP {resp.status_code}"
        except httpx.HTTPError as exc:
            err = f"zone samples network: {type(exc).__name__}"
        except Exception as exc:
            err = f"zone samples malformed ack: {type(exc).__name__}"
        delay = self._bo.next_delay()
        log.warning("%s; retry in %.0fs (%d pending)", err, delay, self.pending)
        return delay

    def run_forever(self, stop: Callable[[], bool]) -> None:
        while not stop():
            interruptible_wait(self.send_once(), stop, self._sleep)

    def close(self) -> None:
        self._client.close()
