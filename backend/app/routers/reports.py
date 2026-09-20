"""Reports (ADR-025): date-range daily totals + previous-period comparison + hour profile, and the multi-store overview.
All bucketing happens in the store's IANA timezone; ranges are capped at MAX_RANGE_DAYS."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import CurrentUser, get_session, require_user
from ..hours import is_open_at
from ..models import CountEvent, Device, Store
from ..schemas import DayBucket, HourProfile, RangeReportOut, RangeTotals, StoreOverviewOut
from .stores import _local_day_range_utc, _store, _today_in

router = APIRouter(prefix="/api/v1", tags=["reports"])

User = Annotated[CurrentUser, Depends(require_user)]
Db = Annotated[AsyncSession, Depends(get_session)]
MAX_RANGE_DAYS = 92
HEARTBEAT_STALE_S = 180  # single definition mirrored from docs/CONTRACTS.md (3 × 60 s)


async def _events_between(s: AsyncSession, store_id: UUID, start: date, end_inclusive: date, tz: ZoneInfo) -> list[tuple[str, datetime]]:
    start_utc, _ = _local_day_range_utc(start, tz)
    _, end_utc = _local_day_range_utc(end_inclusive, tz)
    rows = await s.execute(select(CountEvent.event_type, CountEvent.event_ts)
                           .where(CountEvent.store_id == store_id, CountEvent.event_ts >= start_utc, CountEvent.event_ts < end_utc))
    return [(t, ts) for t, ts in rows.all()]


def _totals(events: list[tuple[str, datetime]], start: date, end: date) -> RangeTotals:
    enter = sum(1 for t, _ in events if t == "enter")
    return RangeTotals(from_date=start, to_date=end, days=(end - start).days + 1, enter=enter, exit=len(events) - enter)


@router.get("/stores/{store_id}/report", response_model=RangeReportOut)
async def range_report(store_id: UUID, s: Db, user: User,
                       from_: Annotated[date, Query(alias="from")], to: Annotated[date, Query()]) -> RangeReportOut:
    store = await _store(s, store_id, user)
    if to < from_:
        raise HTTPException(422, "to must be on or after from")
    days = (to - from_).days + 1
    if days > MAX_RANGE_DAYS:
        raise HTTPException(422, f"range must be at most {MAX_RANGE_DAYS} days")
    tz = ZoneInfo(store.timezone)
    prev_to = from_ - timedelta(days=1)
    prev_from = prev_to - timedelta(days=days - 1)
    current_all = await _events_between(s, store.id, from_, to, tz)
    previous_all = await _events_between(s, store.id, prev_from, prev_to, tz)
    open_ = lambda ts: is_open_at(store, ts.astimezone(tz))  # noqa: E731
    current = [(t, ts) for t, ts in current_all if open_(ts)]
    previous = [(t, ts) for t, ts in previous_all if open_(ts)]

    per_day: dict[date, list[int]] = {from_ + timedelta(days=i): [0, 0] for i in range(days)}
    per_hour = [[0, 0] for _ in range(24)]
    for t, ts in current:
        local = ts.astimezone(tz)
        idx = 0 if t == "enter" else 1
        per_day[local.date()][idx] += 1
        per_hour[local.hour][idx] += 1
    return RangeReportOut(
        store_id=store.id, timezone=store.timezone, open_time=store.open_time, close_time=store.close_time,
        outside_hours_excluded=len(current_all) - len(current),
        current=_totals(current, from_, to), previous=_totals(previous, prev_from, prev_to),
        daily=[DayBucket(date=d, enter=c[0], exit=c[1]) for d, c in per_day.items()],
        hourly_profile=[HourProfile(hour=h, enter=c[0], exit=c[1]) for h, c in enumerate(per_hour)],
    )


@router.get("/overview", response_model=list[StoreOverviewOut])
async def overview(s: Db, user: User) -> list[StoreOverviewOut]:
    if not user.tenant_ids:
        return []
    stores = (await s.execute(select(Store).where(Store.tenant_id.in_(user.tenant_ids)).order_by(Store.created_at))).scalars().all()
    now = datetime.now(timezone.utc)
    out: list[StoreOverviewOut] = []
    for st in stores:
        tz = ZoneInfo(st.timezone)
        today = _today_in(tz)
        events = await _events_between(s, st.id, today - timedelta(days=7), today, tz)
        enter_by_day: dict[date, int] = {}
        exit_today = 0
        for t, ts in events:
            local = ts.astimezone(tz)
            if not is_open_at(st, local):
                continue  # closed hours are not counted (ADR-026)
            d = local.date()
            if t == "enter":
                enter_by_day[d] = enter_by_day.get(d, 0) + 1
            elif d == today:
                exit_today += 1
        last = (await s.execute(select(func.max(CountEvent.event_ts)).where(CountEvent.store_id == st.id))).scalar_one()
        devices = (await s.execute(select(Device).where(Device.store_id == st.id))).scalars().all()
        active = [d for d in devices if d.is_active]
        open_now = is_open_at(st, now.astimezone(tz))
        problem = sum(1 for d in active if d.last_heartbeat_at is None or (now - d.last_heartbeat_at).total_seconds() > HEARTBEAT_STALE_S
                      or d.hb_source_status == "source_down") if open_now else 0
        out.append(StoreOverviewOut(
            store_id=st.id, tenant_id=st.tenant_id, name=st.name, timezone=st.timezone, date=today,
            enter=enter_by_day.get(today, 0), exit=exit_today, yesterday_enter=enter_by_day.get(today - timedelta(days=1), 0),
            avg_enter_7d=round(sum(enter_by_day.get(today - timedelta(days=i), 0) for i in range(1, 8)) / 7, 1),
            last_event_at=last, devices_total=len(active), devices_problem=problem,
            is_open_now=open_now, open_time=st.open_time, close_time=st.close_time,
        ))
    return out
