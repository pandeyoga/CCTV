from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterator

from .base import Frame


class SyntheticSource:
    """Emits image-less frames at a fixed fps. Pair with ScriptedDetector in tests."""

    kind = "synthetic"

    def __init__(self, n_frames: int, fps: float = 10.0, width: int = 640, height: int = 480,
                 start_ts: datetime | None = None) -> None:
        self.n_frames = n_frames
        self.fps = fps
        self.width = width
        self.height = height
        self.start_ts = start_ts or datetime.now(timezone.utc)

    def frames(self) -> Iterator[Frame]:
        for i in range(self.n_frames):
            yield Frame(index=i, ts=self.start_ts + timedelta(seconds=i / self.fps),
                        width=self.width, height=self.height, image=None)

    def close(self) -> None:
        return None
