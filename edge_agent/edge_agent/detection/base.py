from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from ..video.base import Frame

BBox = tuple[float, float, float, float]  # x1, y1, x2, y2 normalized to [0, 1]


@dataclass(frozen=True)
class Detection:
    bbox: BBox
    confidence: float
    class_id: int = 0  # 0 == person (COCO)


class Detector(Protocol):
    """Swappable person detector. Must return normalized bboxes so downstream is resolution-agnostic."""

    name: str

    def detect(self, frame: Frame) -> Sequence[Detection]: ...
