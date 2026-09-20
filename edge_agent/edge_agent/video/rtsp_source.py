from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Callable, Iterator

import cv2

from ..redact import redact_url
from ..transport.backoff import Backoff
from .base import Frame

log = logging.getLogger(__name__)


class RtspVideoSource:
    """Live RTSP stream with reconnect + backoff. Frame ts = wall clock at capture (UTC).

    Every successful (re)connect starts a new `session_id`; frames carry it so the pipeline can reset
    tracker/counter state at a discontinuity instead of reusing stale tracks.
    The URL (which may embed credentials) is never logged; only redact_url(url) is.
    The agent dials out to the camera on the LAN; nothing listens on the internet.
    """

    kind = "rtsp"

    def __init__(self, url: str, reconnect_base_s: float = 1.0, reconnect_max_s: float = 30.0,
                 max_reconnects: int | None = None, sleep: Callable[[float], None] = time.sleep,
                 on_status: Callable[[bool], None] | None = None) -> None:
        self._url = url
        self.safe_url = redact_url(url)
        self.max_reconnects = max_reconnects
        self._backoff = Backoff(reconnect_base_s, reconnect_max_s)
        self._sleep = sleep
        self._on_status = on_status
        self._cap: cv2.VideoCapture | None = None
        self._stopped = False
        self.session_id = 0

    def _open(self) -> bool:
        self._cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
        ok = bool(self._cap.isOpened())
        if self._on_status:
            self._on_status(ok)
        return ok

    def frames(self) -> Iterator[Frame]:
        index = 0
        while not self._stopped:
            if self._cap is None or not self._cap.isOpened():
                if self.max_reconnects is not None and self._backoff.failures > self.max_reconnects:
                    log.error("rtsp source %s: giving up after %d reconnects", self.safe_url, self._backoff.failures)
                    return
                if not self._open():
                    delay = self._backoff.next_delay()
                    log.warning("rtsp source %s unavailable; retry in %.1fs", self.safe_url, delay)
                    self._sleep(delay)
                    continue
                self._backoff.reset()
                self.session_id += 1
                log.info("rtsp source %s connected (session %d)", self.safe_url, self.session_id)
            ok, image = self._cap.read()
            if not ok:
                log.warning("rtsp source %s: read failed; reconnecting", self.safe_url)
                self._cap.release()
                self._cap = None
                if self._on_status:
                    self._on_status(False)
                continue
            h, w = image.shape[:2]
            yield Frame(index=index, ts=datetime.now(timezone.utc), width=w, height=h, image=image, session_id=self.session_id)
            index += 1

    def close(self) -> None:
        self._stopped = True
        if self._cap is not None:
            self._cap.release()
