"""Store opening hours (ADR-026). Times are "HH:MM" in the store's IANA timezone; both NULL => open 24 h.
Overnight ranges (close <= open, e.g. 18:00-02:00) are supported: the window wraps past midnight."""
from __future__ import annotations

import re
from datetime import datetime

from .models import Store

_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def parse_hhmm(value: str) -> int:
    """'HH:MM' -> minutes since midnight; ValueError when malformed."""
    m = _HHMM.match(value)
    if not m:
        raise ValueError("time must be HH:MM (00:00-23:59)")
    return int(m.group(1)) * 60 + int(m.group(2))


def has_hours(store: Store) -> bool:
    return store.open_time is not None and store.close_time is not None


def is_open_at(store: Store, local: datetime) -> bool:
    """`local` must already be in the store timezone. Open at open_time (inclusive), closed at close_time (exclusive)."""
    if not has_hours(store):
        return True
    o, c = parse_hhmm(store.open_time), parse_hhmm(store.close_time)
    minute = local.hour * 60 + local.minute
    if o < c:
        return o <= minute < c
    return minute >= o or minute < c  # overnight window
