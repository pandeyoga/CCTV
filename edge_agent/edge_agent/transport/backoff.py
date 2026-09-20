"""Overflow-safe exponential backoff with jitter. `max_delay_s` bounds the FINAL delay (after jitter)."""
from __future__ import annotations

import random
from typing import Callable

_MAX_EXPONENT = 60  # 2**60 is far beyond any sane max_delay; capping avoids OverflowError


class Backoff:
    def __init__(self, base_s: float, max_s: float, rng: Callable[[], float] = random.random) -> None:
        if base_s <= 0 or max_s < base_s:
            raise ValueError("need 0 < base_s <= max_s")
        self.base_s = base_s
        self.max_s = max_s
        self._rng = rng
        self.failures = 0

    def next_delay(self) -> float:
        """Register a failure and return the delay to wait; in [min(base/2, max), max_s]."""
        self.failures += 1
        raw = min(self.max_s, self.base_s * 2.0 ** min(self.failures - 1, _MAX_EXPONENT))
        return min(self.max_s, raw * (0.5 + self._rng()))  # jitter in [0.5x, 1.5x), then clamp

    def reset(self) -> None:
        self.failures = 0
