from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from ..detection.base import BBox, Detection


@dataclass(frozen=True)
class Track:
    track_id: int  # local, monotonically increasing; NOT a person identity
    bbox: BBox  # normalized
    confidence: float
    hits: int  # consecutive-ish matched frames


class Tracker(Protocol):
    """Swappable multi-object tracker. update() is called once per frame, in order."""

    name: str

    def update(self, detections: Sequence[Detection], frame_index: int) -> Sequence[Track]: ...

    def reset(self) -> None: ...
