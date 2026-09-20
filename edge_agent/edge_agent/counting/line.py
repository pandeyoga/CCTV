from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Literal

# Numerical tolerance for "touching" the segment: an intersection whose parameter along a->b lies in
# [-SEGMENT_EPS, 1 + SEGMENT_EPS] counts as crossing the segment. Touching an endpoint therefore COUNTS.
SEGMENT_EPS = 1e-9


class Side(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    DEADBAND = "deadband"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DirectedLine:
    """Counting line in normalized image coordinates (0..1, origin top-left, y down).

    Direction a -> b defines LEFT/RIGHT as seen on screen when walking from a to b.
    A crossing that ends on `enter_side` is an ENTER; the opposite is an EXIT.
    The line is a finite SEGMENT: paths that change side beyond either endpoint are not crossings.
    """

    line_id: str
    ax: float
    ay: float
    bx: float
    by: float
    enter_side: Literal["left", "right"] = "left"

    def __post_init__(self) -> None:
        for v in (self.ax, self.ay, self.bx, self.by):
            if not 0.0 <= v <= 1.0:
                raise ValueError("line coordinates must be normalized to [0, 1]")
        if self.length == 0.0:
            raise ValueError("line endpoints must differ")
        if self.enter_side not in ("left", "right"):
            raise ValueError("enter_side must be 'left' or 'right'")

    @property
    def length(self) -> float:
        return math.hypot(self.bx - self.ax, self.by - self.ay)

    def signed_distance(self, x: float, y: float) -> float:
        """> 0 => RIGHT of a->b on screen (y-down), < 0 => LEFT. Units: normalized."""
        dx, dy = self.bx - self.ax, self.by - self.ay
        return (dx * (y - self.ay) - dy * (x - self.ax)) / self.length

    def side(self, x: float, y: float, hysteresis: float) -> Side:
        d = self.signed_distance(x, y)
        if abs(d) < hysteresis:
            return Side.DEADBAND
        return Side.RIGHT if d > 0 else Side.LEFT

    def is_enter(self, new_side: Side) -> bool:
        return new_side.value == self.enter_side

    def segment_intersects(self, p: tuple[float, float], q: tuple[float, float], eps: float = SEGMENT_EPS) -> bool:
        """True if the path p->q crosses the finite segment a->b (endpoints inclusive within eps).

        Parallel/collinear paths never count: a collinear walk along the line does not cross it.
        """
        rx, ry = self.bx - self.ax, self.by - self.ay
        sx, sy = q[0] - p[0], q[1] - p[1]
        denom = rx * sy - ry * sx
        if abs(denom) < 1e-15:
            return False
        qpx, qpy = p[0] - self.ax, p[1] - self.ay
        u = (qpx * sy - qpy * sx) / denom  # position along a->b
        t = (qpx * ry - qpy * rx) / denom  # position along p->q
        return -eps <= u <= 1.0 + eps and -eps <= t <= 1.0 + eps
