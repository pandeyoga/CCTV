from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Protocol

import numpy as np


@dataclass(frozen=True)
class Frame:
    index: int
    ts: datetime  # UTC, tz-aware; the *event* time base
    width: int
    height: int
    image: np.ndarray | None  # BGR HxWx3; None for synthetic detector-only runs
    session_id: int = 0  # increments on every (re)connect of a live source; a change means discontinuity


class VideoSource(Protocol):
    kind: str  # "file" | "rtsp" | "synthetic"

    def frames(self) -> Iterator[Frame]: ...

    def close(self) -> None: ...
