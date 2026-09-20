"""Dependency-free IoU tracker with constant-velocity prediction and greedy matching.

Baseline implementation behind the Tracker interface. Replaceable by ByteTrack
(MIT) via an adapter later without touching the counter (see docs/DECISIONS.md ADR-004).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from ..detection.base import BBox, Detection
from .base import Track


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)), dtype=np.float32)
    xx1 = np.maximum(a[:, None, 0], b[None, :, 0])
    yy1 = np.maximum(a[:, None, 1], b[None, :, 1])
    xx2 = np.minimum(a[:, None, 2], b[None, :, 2])
    yy2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / (area_a[:, None] + area_b[None, :] - inter + 1e-9)


@dataclass
class _State:
    track_id: int
    bbox: np.ndarray
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(4, dtype=np.float32))
    hits: int = 1
    misses: int = 0
    confidence: float = 0.0

    def predicted(self) -> np.ndarray:
        return self.bbox + self.velocity


class IouTracker:
    name = "iou"

    def __init__(self, min_iou: float = 0.3, max_age: int = 15, min_hits: int = 2,
                 velocity_smoothing: float = 0.6) -> None:
        self.min_iou = min_iou
        self.max_age = max_age
        self.min_hits = min_hits
        self.velocity_smoothing = velocity_smoothing
        self._tracks: list[_State] = []
        self._next_id = 1

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1

    def update(self, detections: Sequence[Detection], frame_index: int) -> Sequence[Track]:
        det_boxes = np.array([d.bbox for d in detections], dtype=np.float32).reshape(-1, 4)
        pred_boxes = np.array([t.predicted() for t in self._tracks], dtype=np.float32).reshape(-1, 4)
        ious = iou_matrix(pred_boxes, det_boxes)

        matched_t: set[int] = set()
        matched_d: set[int] = set()
        if ious.size:
            order = np.dstack(np.unravel_index(np.argsort(-ious, axis=None), ious.shape))[0]
            for ti, di in order:
                if ious[ti, di] < self.min_iou:
                    break
                if ti in matched_t or di in matched_d:
                    continue
                matched_t.add(int(ti))
                matched_d.add(int(di))
                self._apply_match(self._tracks[ti], det_boxes[di], detections[di].confidence)

        for ti, t in enumerate(self._tracks):
            if ti not in matched_t:
                t.misses += 1
                t.bbox = t.predicted()
        self._tracks = [t for t in self._tracks if t.misses <= self.max_age]

        for di, d in enumerate(detections):
            if di not in matched_d:
                self._tracks.append(_State(track_id=self._next_id, bbox=det_boxes[di].copy(), confidence=d.confidence))
                self._next_id += 1

        return [
            Track(track_id=t.track_id, bbox=_to_bbox(t.bbox), confidence=t.confidence, hits=t.hits)
            for t in self._tracks
            if t.misses == 0 and t.hits >= self.min_hits
        ]

    def _apply_match(self, t: _State, box: np.ndarray, confidence: float) -> None:
        new_velocity = box - t.bbox
        t.velocity = self.velocity_smoothing * t.velocity + (1 - self.velocity_smoothing) * new_velocity
        t.bbox = box.copy()
        t.hits += 1
        t.misses = 0
        t.confidence = confidence


def _to_bbox(arr: np.ndarray) -> BBox:
    return (float(arr[0]), float(arr[1]), float(arr[2]), float(arr[3]))
