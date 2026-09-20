"""Dashboard read endpoints. Buckets are computed in the store's IANA timezone (ADR-008)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import CurrentUser, get_session, require_user
from ..models import CountEvent, Device, Store
from ..schemas import DeviceOut, HourBucket, HourlyOut, StoreOut, SummaryOut
from .devices import device_fields

router = APIRouter(prefix="/api/v1/stores", tags=["stores"])

User = Annotated[CurrentUser, Depends(require_user)]


async def _store(session: AsyncSession, store_id: UUID, user: CurrentUser) -> Store:
    """404 for both unknown and not-permitted stores: a known UUID is not a permission."""
    store = await session.get(Store, store_id)
    if store is None or store.tenant_id not in user.tenant_ids:
        raise HTTPException(404, "store not found")
    return store


def _local_day_range_utc(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start_local = datetime(day.year, day.month, day.day, tzinfo=tz)
    return start_local.astimezone(ZoneInfo("UTC")), (start_local + timedelta(days=1)).astimezone(ZoneInfo("UTC"))


async def _day_events(session: AsyncSession, store: Store, day: date) -> tuple[ZoneInfo, list[tuple[str, datetime]]]:
    tz = ZoneInfo(store.timezone)
    start_utc, end_utc = _local_day_range_utc(day, tz)
    rows = await session.execute(
        select(CountEvent.event_type, CountEvent.event_ts)
        .where(CountEvent.store_id == store.id, CountEvent.event_ts >= start_utc, CountEvent.event_ts < end_utc)
    )
    return tz, [(t, ts) for t, ts in rows.all()]


def _today_in(tz: ZoneInfo) -> date:
    return datetime.now(tz).date()


@router.get("", response_model=list[StoreOut])
async def list_stores(session: Annotated[AsyncSession, Depends(get_session)], user: User) -> list[StoreOut]:
    if not user.tenant_ids:
        return []
    rows = (await session.execute(select(Store).where(Store.tenant_id.in_(user.tenant_ids)).order_by(Store.created_at))).scalars()
    return [StoreOut(store_id=s.id, tenant_id=s.tenant_id, name=s.name, timezone=s.timezone, open_time=s.open_time, close_time=s.close_time,
                     telegram_chat_id=s.telegram_chat_id) for s in rows]


@router.get("/{store_id}/summary", response_model=SummaryOut)
async def summary(store_id: UUID, session: Annotated[AsyncSession, Depends(get_session)], user: User,
                  day: Annotated[date | None, Query(alias="date")] = None) -> SummaryOut:
    store = await _store(session, store_id, user)
    tz = ZoneInfo(store.timezone)
    day = day or _today_in(tz)
    _, events = await _day_events(session, store, day)
    enter = sum(1 for t, _ in events if t == "enter")
    exit_ = len(events) - enter
    last = (await session.execute(
        select(func.max(CountEvent.event_ts)).where(CountEvent.store_id == store.id))).scalar_one()
    return SummaryOut(store_id=store.id, date=day, timezone=store.timezone, enter=enter, exit=exit_,
                      occupancy_estimate=enter - exit_, last_event_at=last)


@router.get("/{store_id}/hourly", response_model=HourlyOut)
async def hourly(store_id: UUID, session: Annotated[AsyncSession, Depends(get_session)], user: User,
                 day: Annotated[date | None, Query(alias="date")] = None) -> HourlyOut:
    store = await _store(session, store_id, user)
    tz = ZoneInfo(store.timezone)
    day = day or _today_in(tz)
    _, events = await _day_events(session, store, day)
    start_local = datetime(day.year, day.month, day.day, tzinfo=tz)
    counts = [[0, 0] for _ in range(24)]
    for t, ts in events:
        h = ts.astimezone(tz).hour
        counts[h][0 if t == "enter" else 1] += 1
    buckets = [HourBucket(hour_start=start_local + timedelta(hours=h), enter=c[0], exit=c[1]) for h, c in enumerate(counts)]
    return HourlyOut(store_id=store.id, date=day, timezone=store.timezone, buckets=buckets)


@router.get("/{store_id}/devices", response_model=list[DeviceOut])
async def devices(store_id: UUID, session: Annotated[AsyncSession, Depends(get_session)], user: User) -> list[DeviceOut]:
    store = await _store(session, store_id, user)
    rows = (await session.execute(select(Device).where(Device.store_id == store.id).order_by(Device.created_at))).scalars()
    return [DeviceOut(**device_fields(d)) for d in rows]
