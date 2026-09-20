"""Server-side configuration pull (ADR-030): GET /api/v1/devices/me/config every `interval_s`; when `config_version`
differs from the last applied one, `on_config` is called with the validated DeviceConfigV1 (any thread-safe consumer).
Failures back off (bounded) and never touch the running configuration."""
from __future__ import annotations

import logging
import time
from typing import Callable

import httpx

from ..contracts import DeviceConfigV1
from .backoff import Backoff
from .sender import interruptible_wait

log = logging.getLogger(__name__)
CONFIG_PATH = "/api/v1/devices/me/config"


class ConfigPoller:
    def __init__(self, backend_url: str, api_key: str, on_config: Callable[[DeviceConfigV1], None], interval_s: float = 300.0,
                 client: httpx.Client | None = None, timeout_s: float = 10.0, max_backoff_s: float = 900.0,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if not api_key:
            raise ValueError("api key is required (EDGE_API_KEY)")
        if interval_s <= 0:
            raise ValueError("interval_s must be > 0")
        self.interval_s = interval_s
        self._on_config = on_config
        self._client = client or httpx.Client(timeout=timeout_s)
        self._url = backend_url.rstrip("/") + CONFIG_PATH
        self._headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        self._bo = Backoff(interval_s, max(max_backoff_s, interval_s))
        self._sleep = sleep
        self.applied_version: str | None = None
        self.polls = 0
        self.failed = 0

    def poll_once(self) -> float:
        """One request; applies the config when the version changed. Returns the delay before the next poll."""
        try:
            resp = self._client.get(self._url, headers=self._headers)
            if resp.status_code == 200:
                cfg = DeviceConfigV1.model_validate(resp.json())
                self.polls += 1
                self._bo.reset()
                if cfg.config_version != self.applied_version:
                    self._on_config(cfg)
                    self.applied_version = cfg.config_version
                    log.info("device config applied version=%s cameras=%d", cfg.config_version, len(cfg.cameras))
                return self.interval_s
            err = f"config HTTP {resp.status_code}"
        except httpx.HTTPError as exc:
            err = f"config network: {type(exc).__name__}"
        except Exception as exc:  # malformed body or consumer error: keep the running config
            err = f"config invalid/apply failed: {type(exc).__name__}"
        self.failed += 1
        delay = self._bo.next_delay()
        log.warning("%s; next config poll in %.0fs", err, delay)
        return delay

    def run_forever(self, stop: Callable[[], bool]) -> None:
        while not stop():
            interruptible_wait(self.poll_once(), stop, self._sleep)

    def close(self) -> None:
        self._client.close()
