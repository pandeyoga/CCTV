"""Drawing helpers for calibration and annotated review videos (pixels derived from normalized coords)."""
from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np

from ..counting.counter import Crossing, anchor_point
from ..counting.line import DirectedLine
from ..tracking.base import Track

GREEN = (80, 220, 100)
RED = (80, 80, 240)
CYAN = (240, 200, 60)
WHITE = (240, 240, 240)


def _px(x: float, y: float, w: int, h: int) -> tuple[int, int]:
    return int(round(x * w)), int(round(y * h))


def draw_grid(img: np.ndarray, step: float = 0.1) -> np.ndarray:
    h, w = img.shape[:2]
    n = int(round(1 / step))
    for i in range(1, n):
        v = i * step
        cv2.line(img, (int(v * w), 0), (int(v * w), h), (90, 90, 90), 1)
        cv2.line(img, (0, int(v * h)), (w, int(v * h)), (90, 90, 90), 1)
        cv2.putText(img, f"{v:.1f}", (int(v * w) + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, WHITE, 1)
        cv2.putText(img, f"{v:.1f}", (2, int(v * h) - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, WHITE, 1)
    return img


def draw_line(img: np.ndarray, line: DirectedLine) -> np.ndarray:
    h, w = img.shape[:2]
    a, b = _px(line.ax, line.ay, w, h), _px(line.bx, line.by, w, h)
    cv2.arrowedLine(img, a, b, CYAN, 2, tipLength=0.05)
    # arrow toward the ENTER side from the line midpoint
    mx, my = (line.ax + line.bx) / 2, (line.ay + line.by) / 2
    dx, dy = (line.bx - line.ax) / line.length, (line.by - line.ay) / line.length
    nx, ny = (-dy, dx) if line.enter_side == "right" else (dy, -dx)  # screen normal toward enter side
    cv2.arrowedLine(img, _px(mx, my, w, h), _px(mx + nx * 0.08, my + ny * 0.08, w, h), GREEN, 2, tipLength=0.3)
    cv2.putText(img, f"{line.line_id} enter->", _px(mx + nx * 0.09, my + ny * 0.09, w, h), cv2.FONT_HERSHEY_SIMPLEX, 0.5, GREEN, 1)
    return img


def draw_tracks(img: np.ndarray, tracks: Sequence[Track], anchor: str = "bottom_center") -> np.ndarray:
    h, w = img.shape[:2]
    for t in tracks:
        x1, y1, x2, y2 = t.bbox
        cv2.rectangle(img, _px(x1, y1, w, h), _px(x2, y2, w, h), GREEN, 2)
        ax, ay = anchor_point(t, anchor)  # type: ignore[arg-type]
        cv2.circle(img, _px(ax, ay, w, h), 4, CYAN, -1)
        cv2.putText(img, f"#{t.track_id}", _px(x1, y1, w, h), cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1)
    return img


def draw_crossings(img: np.ndarray, crossings: Sequence[Crossing]) -> np.ndarray:
    h, w = img.shape[:2]
    for c in crossings:
        color = GREEN if c.event_type.value == "enter" else RED
        cv2.circle(img, _px(c.x, c.y, w, h), 14, color, 3)
        cv2.putText(img, c.event_type.value.upper(), _px(c.x + 0.02, c.y, w, h), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return img


def draw_counts(img: np.ndarray, enter: int, exit_: int, frame_index: int) -> np.ndarray:
    cv2.rectangle(img, (0, 0), (260, 28), (0, 0, 0), -1)
    cv2.putText(img, f"IN {enter}  OUT {exit_}  f{frame_index}", (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, WHITE, 1)
    return img
