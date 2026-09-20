"""POST /api/v1/devices/heartbeat — device liveness, scoped to the authenticated device only; every heartbeat is also
appended to `device_heartbeats` (ADR-027, pruned per device to HEARTBEAT_RETENTION_DAYS).
GET  /api/v1/devices                    — dashboard: every device across the user's permitted stores.
GET  /api/v1/devices/{id}/heartbeats    — dashboard: up/down timeline for one device (default last 24 h)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import CurrentUser, get_session, require_device, require_user
from ..contracts import HeartbeatAckV1, HeartbeatV1
from ..models import HEARTBEAT_RETENTION_DAYS, Device, DeviceHeartbeat, Store
from ..schemas import DeviceWithStoreOut, HeartbeatHistoryOut, HeartbeatSegment

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])

HEARTBEAT_STALE_S = 180  # 3 × 60 s interval — single definition shared with docs/CONTRACTS.md and frontend lib/time.ts
MAX_HISTORY_HOURS = 24 * HEARTBEAT_RETENTION_DAYS


def device_fields(d: Device) -> dict:
    return dict(device_id=d.id, name=d.name, is_active=d.is_active, last_event_at=d.last_seen_at,
                last_heartbeat_at=d.last_heartbeat_at, source_status=d.hb_source_status,
                last_frame_age_s=d.hb_last_frame_age_s, pending_events=d.hb_pending_events,
                agent_version=d.hb_agent_version)


@router.post("/heartbeat", response_model=HeartbeatAckV1)
async def heartbeat(
    body: HeartbeatV1,
    device: Annotated[Device, Depends(require_device)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HeartbeatAckV1:
    received_at = datetime.now(timezone.utc)  # server clock; body.sent_at is informational only
    device.last_heartbeat_at = received_at
    device.hb_source_status = body.source_status
    device.hb_last_frame_age_s = body.last_frame_age_s
    device.hb_pending_events = body.pending_events
    device.hb_tracking_session_id = body.tracking_session_id
    device.hb_agent_version = body.agent_version
    session.add(DeviceHeartbeat(tenant_id=device.tenant_id, device_id=device.id, received_at=received_at,
                                source_status=body.source_status, last_frame_age_s=body.last_frame_age_s,
                                pending_events=body.pending_events, tracking_session_id=body.tracking_session_id,
                                agent_version=body.agent_version))
    await session.execute(delete(DeviceHeartbeat).where(DeviceHeartbeat.device_id == device.id,
                                                        DeviceHeartbeat.received_at < received_at - timedelta(days=HEARTBEAT_RETENTION_DAYS)))
    await session.commit()
    return HeartbeatAckV1(received_at=received_at)


@router.get("", response_model=list[DeviceWithStoreOut])
async def list_devices(session: Annotated[AsyncSession, Depends(get_session)],
                       user: Annotated[CurrentUser, Depends(require_user)]) -> list[DeviceWithStoreOut]:
    if not user.tenant_ids:
        return []
    rows = await session.execute(
        select(Device, Store).join(Store, Device.store_id == Store.id)
        .where(Store.tenant_id.in_(user.tenant_ids)).order_by(Store.created_at, Device.created_at)
    )
    return [DeviceWithStoreOut(**device_fields(d), store_id=s.id, store_name=s.name, store_timezone=s.timezone)
            for d, s in rows.all()]


def build_segments(samples: list[tuple[datetime, str]], start: datetime, end: datetime, stale_after_s: int) -> list[HeartbeatSegment]:
    """Pure function (tested directly). `samples` sorted by time, may include one sample before `start` for context."""
    stale = timedelta(seconds=stale_after_s)
    segs: list[HeartbeatSegment] = []

    def push(a: datetime, b: datetime, status: str) -> None:
        a, b = max(a, start), min(b, end)
        if b <= a:
            return
        if segs and segs[-1].status == status and segs[-1].end == a:
            segs[-1] = HeartbeatSegment(start=segs[-1].start, end=b, status=status)  # merge adjacent equal states
        else:
            segs.append(HeartbeatSegment(start=a, end=b, status=status))  # type: ignore[arg-type]

    if not samples:
        push(start, end, "unknown")
        return segs
    if samples[0][0] > start:
        push(start, samples[0][0], "unknown")
    for (t, st), nxt in zip(samples, samples[1:] + [None]):
        status = "camera_down" if st == "source_down" else "connected"
        until = nxt[0] if nxt else end
        if until - t <= stale:
            push(t, until, status)
        else:
            push(t, t + stale, status)
            push(t + stale, until, "stale")
    return segs


@router.get("/{device_id}/heartbeats", response_model=HeartbeatHistoryOut)
async def heartbeat_history(device_id: UUID, session: Annotated[AsyncSession, Depends(get_session)],
                            user: Annotated[CurrentUser, Depends(require_user)],
                            hours: Annotated[int, Query(ge=1, le=MAX_HISTORY_HOURS)] = 24) -> HeartbeatHistoryOut:
    device = await session.get(Device, device_id)
    if device is None or device.tenant_id not in user.tenant_ids:
        raise HTTPException(404, "device not found")
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    rows = (await session.execute(
        select(DeviceHeartbeat.received_at, DeviceHeartbeat.source_status)
        .where(DeviceHeartbeat.device_id == device.id, DeviceHeartbeat.received_at >= start - timedelta(seconds=HEARTBEAT_STALE_S))
        .order_by(DeviceHeartbeat.received_at))).all()
    samples = [(t, s) for t, s in rows]
    segments = build_segments(samples, start, end, HEARTBEAT_STALE_S)
    up = sum((sg.end - sg.start).total_seconds() for sg in segments if sg.status == "connected")
    return HeartbeatHistoryOut(device_id=device.id, from_ts=start, to_ts=end, stale_after_s=HEARTBEAT_STALE_S,
                               samples=sum(1 for t, _ in samples if t >= start),
                               uptime_pct=round(100 * up / (end - start).total_seconds(), 1), segments=segments)
