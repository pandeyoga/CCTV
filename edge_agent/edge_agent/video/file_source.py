from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import cv2

from .base import Frame


class FileVideoSource:
    """Recorded video. Frame ts = start_ts + index/fps (video time, not processing wall-clock)."""

    kind = "file"

    def __init__(self, path: str | Path, start_ts: datetime | None = None, fps_override: float | None = None) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        self._cap = cv2.VideoCapture(str(self.path))
        if not self._cap.isOpened():
            raise RuntimeError(f"cannot open video file {self.path}")
        fps = fps_override or self._cap.get(cv2.CAP_PROP_FPS) or 0.0
        if fps <= 0:
            raise RuntimeError("video fps unknown; pass fps_override")
        self.fps = float(fps)
        self.width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.start_ts = (start_ts or datetime.now(timezone.utc)).astimezone(timezone.utc)

    def frames(self) -> Iterator[Frame]:
        index = 0
        while True:
            ok, image = self._cap.read()
            if not ok:
                return
            h, w = image.shape[:2]
            yield Frame(index=index, ts=self.start_ts + timedelta(seconds=index / self.fps),
                        width=w, height=h, image=image)
            index += 1

    def close(self) -> None:
        self._cap.release()
