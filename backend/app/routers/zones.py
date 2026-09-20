"""Zone occupancy (ADR-031).
Edge:      POST /api/v1/zones/samples — idempotent batch, scoped to the authenticated device (camera/zone by external id).
Dashboard: GET  /api/v1/stores/{id}/zones/occupancy?date= — 24 store-local hour buckets per zone (avg/max of samples)."""
from __future__ import annotations

from datetime import date as date_t, datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import CurrentUser, get_session, require_device, require_user
from ..contracts import RejectedSampleV1, ZoneSampleBatchRequestV1, ZoneSampleBatchResponseV1
from ..models import Camera, Device, Zone, ZoneSample
from ..schemas import ZoneHourBucket, ZoneOccupancyOut, ZoneSeriesOut
from .manage import _visible_store

router = APIRouter(prefix="/api/v1", tags=["zones"])
Db = Annotated[AsyncSession, Depends(get_session)]


@router.post("/zones/samples", response_model=ZoneSampleBatchResponseV1)
async def ingest_samples(body: ZoneSampleBatchRequestV1, device: Annotated[Device, Depends(require_device)], s: Db) -> ZoneSampleBatchResponseV1:
    received_at = datetime.now(timezone.utc)
    cams = {c.external_id: c for c in (await s.execute(select(Camera).where(Camera.store_id == device.store_id,
                                                                            Camera.external_id.in_({x.camera_id for x in body.samples})))).scalars()
            if c.device_id is None or c.device_id == device.id}
    zones = {(z.camera_id, z.external_id): z for z in (await s.execute(select(Zone).where(Zone.camera_id.in_([c.id for c in cams.values()])))).scalars()} if cams else {}
    ids = [x.sample_id for x in body.samples]
    existing = set((await s.execute(select(ZoneSample.sample_id).where(ZoneSample.sample_id.in_(ids)))).scalars())
    accepted, duplicates, rejected, seen = [], [], [], set()
    for x in body.samples:
        if x.sample_id in existing or x.sample_id in seen:
            duplicates.append(x.sample_id)
            continue
        cam = cams.get(x.camera_id)
        zone = zones.get((cam.id, x.zone_id)) if cam else None
        if cam is None or zone is None:
            rejected.append(RejectedSampleV1(sample_id=x.sample_id, reason="unknown camera" if cam is None else "unknown zone"))
            continue
        try:
            async with s.begin_nested():
                s.add(ZoneSample(sample_id=x.sample_id, tenant_id=device.tenant_id, store_id=device.store_id, camera_id=cam.id, zone_id=zone.id,
                                 device_id=device.id, sample_ts=x.sample_ts, received_at=received_at, interval_s=x.interval_s,
                                 count=x.count, count_max=x.count_max))
                await s.flush()
        except IntegrityError:
            duplicates.append(x.sample_id)
            continue
        seen.add(x.sample_id)
        accepted.append(x.sample_id)
    await s.commit()
    return ZoneSampleBatchResponseV1(accepted=accepted, duplicates=duplicates, rejected=rejected)


def bucketize(samples: list[tuple[UUID, datetime, int, int]], day_start: datetime) -> dict[UUID, list[ZoneHourBucket]]:
    """Pure: (zone_id, sample_ts, count, count_max) -> 24 buckets per zone (store-local hours from day_start)."""
    acc: dict[UUID, list[list[int]]] = {}
    for zid, ts, c, m in samples:
        h = int((ts - day_start).total_seconds() // 3600)
        if 0 <= h < 24:
            b = acc.setdefault(zid, [[0, 0, 0] for _ in range(24)])[h]
            b[0] += c
            b[1] = max(b[1], m)
            b[2] += 1
    return {zid: [ZoneHourBucket(hour_start=day_start + timedelta(hours=h), avg_count=round(b[0] / b[2], 2) if b[2] else 0.0,
                                 max_count=b[1], samples=b[2]) for h, b in enumerate(rows)] for zid, rows in acc.items()}


@router.get("/stores/{store_id}/zones/occupancy", response_model=ZoneOccupancyOut)
async def zone_occupancy(store_id: UUID, s: Db, user: Annotated[CurrentUser, Depends(require_user)], date: date_t | None = None) -> ZoneOccupancyOut:
    st = await _visible_store(s, store_id, user)
    tz = ZoneInfo(st.timezone)
    day = date or datetime.now(tz).date()
    day_start = datetime.combine(day, datetime.min.time(), tzinfo=tz)
    zones = (await s.execute(select(Zone).where(Zone.store_id == st.id).order_by(Zone.created_at))).scalars().all()
    rows = (await s.execute(select(ZoneSample.zone_id, ZoneSample.sample_ts, ZoneSample.count, ZoneSample.count_max)
                            .where(ZoneSample.store_id == st.id, ZoneSample.sample_ts >= day_start, ZoneSample.sample_ts < day_start + timedelta(days=1)))).all()
    per_zone = bucketize([(zid, ts, c, m) for zid, ts, c, m in rows], day_start)
    empty = [ZoneHourBucket(hour_start=day_start + timedelta(hours=h), avg_count=0.0, max_count=0, samples=0) for h in range(24)]
    return ZoneOccupancyOut(store_id=st.id, date=day, timezone=st.timezone,
                            zones=[ZoneSeriesOut(zone_id=z.id, name=z.name, external_id=z.external_id, buckets=per_zone.get(z.id, empty),
                                                 samples=sum(b.samples for b in per_zone.get(z.id, empty)),
                                                 peak=max(b.max_count for b in per_zone.get(z.id, empty))) for z in zones])
