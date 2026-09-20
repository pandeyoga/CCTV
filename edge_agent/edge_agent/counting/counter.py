"""Directed line-crossing counter with per-track state and hysteresis.

Rules (see docs/ARCHITECTURE.md "Counting semantics"):
- A track has a `confirmed_side` (UNKNOWN until it is first seen clearly on one side).
- Points inside the deadband (|dist| < hysteresis) never change state, but are recorded on the path.
- A side change is *confirmed* when a track with a known confirmed side is observed on the opposite
  side for `min_confirm_frames` consecutive non-deadband frames.
- A confirmed side change is a *crossing* only if the recorded path (last point on the old side ->
  deadband points -> candidate points) intersects the finite line SEGMENT (endpoints inclusive,
  `line.SEGMENT_EPS`). Otherwise the person walked around an endpoint: the side is updated silently
  and no event is emitted.
- A new/re-appearing track id starts UNKNOWN, so track loss + re-id can never create a crossing
  by itself (it may cause an undercount, never a phantom count).
- Track state expires after `track_ttl_frames` without an observation; `reset()` drops all track
  state (stream reconnect) but keeps the running totals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Sequence

from ..contracts import EventType
from ..tracking.base import Track
from .line import DirectedLine, Side

Anchor = Literal["bottom_center", "center"]
MAX_PATH_POINTS = 64  # bounded history while a track is off its confirmed side


@dataclass(frozen=True)
class Crossing:
    track_id: int
    event_type: EventType
    line_id: str
    frame_index: int
    x: float
    y: float


@dataclass
class _TrackState:
    confirmed_side: Side = Side.UNKNOWN
    candidate_side: Side = Side.UNKNOWN
    candidate_frames: int = 0
    last_seen_frame: int = 0
    path: list[tuple[float, float]] = field(default_factory=list)  # [last point on confirmed side, ...off-side points]


def anchor_point(track: Track, anchor: Anchor) -> tuple[float, float]:
    x1, y1, x2, y2 = track.bbox
    if anchor == "center":
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
    return ((x1 + x2) / 2.0, y2)


class CrossingCounter:
    def __init__(self, line: DirectedLine, hysteresis: float = 0.02, min_confirm_frames: int = 2,
                 track_ttl_frames: int = 30, anchor: Anchor = "bottom_center") -> None:
        if hysteresis < 0:
            raise ValueError("hysteresis must be >= 0")
        if min_confirm_frames < 1:
            raise ValueError("min_confirm_frames must be >= 1")
        self.line = line
        self.hysteresis = hysteresis
        self.min_confirm_frames = min_confirm_frames
        self.track_ttl_frames = track_ttl_frames
        self.anchor = anchor
        self._states: dict[int, _TrackState] = {}
        self.enter_count = 0
        self.exit_count = 0

    @property
    def active_tracks(self) -> int:
        return len(self._states)

    def update(self, tracks: Sequence[Track], frame_index: int) -> list[Crossing]:
        crossings: list[Crossing] = []
        for track in tracks:
            st = self._states.setdefault(track.track_id, _TrackState(last_seen_frame=frame_index))
            st.last_seen_frame = frame_index
            pt = anchor_point(track, self.anchor)
            observed = self.line.side(pt[0], pt[1], self.hysteresis)

            if observed is st.confirmed_side:
                st.candidate_side, st.candidate_frames = Side.UNKNOWN, 0
                st.path = [pt]
                continue

            if len(st.path) < MAX_PATH_POINTS:
                st.path.append(pt)
            if observed is Side.DEADBAND:
                st.candidate_side, st.candidate_frames = Side.UNKNOWN, 0
                continue

            if st.candidate_side is observed:
                st.candidate_frames += 1
            else:
                st.candidate_side, st.candidate_frames = observed, 1
            if st.candidate_frames < self.min_confirm_frames:
                continue

            if st.confirmed_side is not Side.UNKNOWN and self._path_crosses_segment(st.path):
                event_type = EventType.ENTER if self.line.is_enter(observed) else EventType.EXIT
                if event_type is EventType.ENTER:
                    self.enter_count += 1
                else:
                    self.exit_count += 1
                crossings.append(Crossing(track.track_id, event_type, self.line.line_id, frame_index, pt[0], pt[1]))
            st.confirmed_side = observed
            st.candidate_side, st.candidate_frames = Side.UNKNOWN, 0
            st.path = [pt]

        self._expire(frame_index)
        return crossings

    def _path_crosses_segment(self, path: Sequence[tuple[float, float]]) -> bool:
        return any(self.line.segment_intersects(path[i], path[i + 1]) for i in range(len(path) - 1))

    def _expire(self, frame_index: int) -> None:
        dead = [tid for tid, st in self._states.items() if frame_index - st.last_seen_frame > self.track_ttl_frames]
        for tid in dead:
            del self._states[tid]

    def forget(self, track_id: int) -> None:
        self._states.pop(track_id, None)

    def reset(self) -> None:
        """Drop all per-track state (new stream session). Totals are kept."""
        self._states.clear()
