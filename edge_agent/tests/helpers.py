from __future__ import annotations

from edge_agent.detection import Detection
from edge_agent.tracking import Track


def box_at(cx: float, foot_y: float, w: float = 0.1, h: float = 0.3) -> tuple[float, float, float, float]:
    """Normalized bbox whose bottom-center anchor is (cx, foot_y)."""
    return (cx - w / 2, foot_y - h, cx + w / 2, foot_y)


def track(track_id: int, cx: float, foot_y: float) -> Track:
    return Track(track_id=track_id, bbox=box_at(cx, foot_y), confidence=0.9, hits=5)


def det(cx: float, foot_y: float, conf: float = 0.9) -> Detection:
    return Detection(bbox=box_at(cx, foot_y), confidence=conf)


def walk(y_from: float, y_to: float, steps: int) -> list[float]:
    return [y_from + (y_to - y_from) * i / (steps - 1) for i in range(steps)]
