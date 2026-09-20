"""Zone occupancy sampling (ADR-031). Pure geometry + per-interval aggregation, no I/O.

`count` = tracks whose anchor point is inside the polygon at the sampling instant;
`count_max` = maximum simultaneous tracks inside during the interval. Track ids are never persisted."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence
from uuid import uuid4

from ..contracts import ZoneSampleV1
from ..tracking.base import Track
from .counter import Anchor, anchor_point


@dataclass(frozen=True)
class Zone:
    zone_id: str
    polygon: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        if len(self.polygon) < 3:
            raise ValueError("polygon needs at least 3 vertices")


def point_in_polygon(x: float, y: float, polygon: Sequence[tuple[float, float]]) -> bool:
    """Even-odd ray casting; vertices on the boundary count as inside-or-outside consistently (not special-cased)."""
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xin = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < xin:
                inside = not inside
    return inside


class ZoneSampler:
    def __init__(self, camera_id: str, zones: Sequence[Zone], interval_s: float, anchor: Anchor = "bottom_center") -> None:
        if interval_s <= 0:
            raise ValueError("interval_s must be > 0")
        self.camera_id = camera_id
        self.interval = timedelta(seconds=interval_s)
        self.anchor = anchor
        self._zones: list[Zone] = []
        self._max: dict[str, int] = {}
        self._window_start: datetime | None = None
        self.set_zones(zones)

    @property
    def zones(self) -> list[Zone]:
        return list(self._zones)

    def set_zones(self, zones: Sequence[Zone]) -> None:
        """Replace zones (server config reload). Running maxima are dropped; the current window restarts."""
        self._zones = list(zones)
        self._max = {z.zone_id: 0 for z in self._zones}
        self._window_start = None

    def counts(self, tracks: Sequence[Track]) -> dict[str, int]:
        pts = [anchor_point(t, self.anchor) for t in tracks]
        return {z.zone_id: sum(1 for x, y in pts if point_in_polygon(x, y, z.polygon)) for z in self._zones}

    def update(self, tracks: Sequence[Track], ts: datetime) -> list[ZoneSampleV1]:
        """Call once per processed frame. Emits one sample per zone when the interval has elapsed."""
        if not self._zones:
            return []
        if self._window_start is None:
            self._window_start = ts
        now_counts = self.counts(tracks)
        for zid, c in now_counts.items():
            if c > self._max[zid]:
                self._max[zid] = c
        if ts - self._window_start < self.interval:
            return []
        out = [ZoneSampleV1(sample_id=uuid4(), camera_id=self.camera_id, zone_id=zid, sample_ts=ts, interval_s=self.interval.total_seconds(),
                            count=now_counts[zid], count_max=self._max[zid]) for zid in now_counts]
        self._max = {zid: now_counts[zid] for zid in now_counts}
        self._window_start = ts
        return out
