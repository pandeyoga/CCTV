"""Periodic camera snapshot upload (ADR-030): the latest processed frame, downscaled and JPEG-encoded, is POSTed to
/api/v1/devices/snapshot so owners can draw lines/zones on a real picture. Latest-only, never queued."""
from __future__ import annotations

import logging
import time
from typing import Callable

import httpx
import numpy as np

from .backoff import Backoff
from .sender import interruptible_wait

log = logging.getLogger(__name__)
SNAPSHOT_PATH = "/api/v1/devices/snapshot"


def encode_jpeg(image: np.ndarray, max_width: int = 960, quality: int = 70) -> bytes:
    import cv2  # lazy: tests without a frame never need it
    h, w = image.shape[:2]
    if w > max_width:
        image = cv2.resize(image, (max_width, int(h * max_width / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError("jpeg encode failed")
    return bytes(buf)


class SnapshotUploader:
    def __init__(self, camera_id: str, get_image: Callable[[], np.ndarray | None], backend_url: str, api_key: str, interval_s: float = 600.0,
                 client: httpx.Client | None = None, timeout_s: float = 15.0, max_backoff_s: float = 1800.0,
                 sleep: Callable[[float], None] = time.sleep, encode: Callable[[np.ndarray], bytes] = encode_jpeg) -> None:
        if not api_key:
            raise ValueError("api key is required (EDGE_API_KEY)")
        if interval_s <= 0:
            raise ValueError("interval_s must be > 0")
        self.interval_s = interval_s
        self._get_image = get_image
        self._client = client or httpx.Client(timeout=timeout_s)
        self._url = backend_url.rstrip("/") + SNAPSHOT_PATH
        self._params = {"camera_id": camera_id}
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "image/jpeg"}
        self._bo = Backoff(interval_s, max(max_backoff_s, interval_s))
        self._sleep = sleep
        self._encode = encode
        self.sent = 0
        self.failed = 0

    def send_once(self) -> float:
        image = self._get_image()
        if image is None:
            return self.interval_s  # no frame yet (source down / synthetic run)
        try:
            resp = self._client.post(self._url, params=self._params, content=self._encode(image), headers=self._headers)
            if resp.status_code == 200:
                self.sent += 1
                self._bo.reset()
                return self.interval_s
            err = f"snapshot HTTP {resp.status_code}"
        except httpx.HTTPError as exc:
            err = f"snapshot network: {type(exc).__name__}"
        except Exception as exc:
            err = f"snapshot encode failed: {type(exc).__name__}"
        self.failed += 1
        delay = self._bo.next_delay()
        log.warning("%s; next snapshot in %.0fs", err, delay)
        return delay

    def run_forever(self, stop: Callable[[], bool]) -> None:
        while not stop():
            interruptible_wait(self.send_once(), stop, self._sleep)

    def close(self) -> None:
        self._client.close()
