"""POST /api/v1/events/batch — idempotent ingest scoped to the authenticated device."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_session, require_device
from ..contracts import CountEventV1, EventBatchRequestV1, EventBatchResponseV1, RejectedEventV1
from ..models import Camera, CountEvent, Device

router = APIRouter(prefix="/api/v1/events", tags=["events"])

REASON_UNKNOWN_CAMERA = "unknown camera"


async def _camera_map(session: AsyncSession, device: Device, external_ids: set[str]) -> dict[str, Camera]:
    if not external_ids:
        return {}
    rows = await session.execute(
        select(Camera).where(Camera.store_id == device.store_id, Camera.external_id.in_(external_ids))
    )
    cams = {c.external_id: c for c in rows.scalars() if c.device_id is None or c.device_id == device.id}
    return cams


def _to_row(ev: CountEventV1, device: Device, camera: Camera, received_at: datetime) -> CountEvent:
    return CountEvent(
        event_id=ev.event_id, tenant_id=device.tenant_id, store_id=device.store_id, device_id=device.id,
        camera_id=camera.id, line_id=ev.line_id, event_type=ev.event_type.value, event_ts=ev.event_ts,
        received_at=received_at, track_id=ev.track_id, frame_index=ev.frame_index,
        source_kind=ev.source_kind, schema_version=ev.schema_version, tracking_session_id=ev.tracking_session_id,
    )


@router.post("/batch", response_model=EventBatchResponseV1)
async def ingest_batch(
    body: EventBatchRequestV1,
    device: Annotated[Device, Depends(require_device)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EventBatchResponseV1:
    received_at = datetime.now(timezone.utc)
    cameras = await _camera_map(session, device, {e.camera_id for e in body.events})
    ids = [e.event_id for e in body.events]
    existing: set[UUID] = set(
        (await session.execute(select(CountEvent.event_id).where(CountEvent.event_id.in_(ids)))).scalars()
    )

    accepted: list[UUID] = []
    duplicates: list[UUID] = []
    rejected: list[RejectedEventV1] = []
    seen_in_batch: set[UUID] = set()
    for ev in body.events:
        if ev.event_id in existing or ev.event_id in seen_in_batch:
            duplicates.append(ev.event_id)
            continue
        camera = cameras.get(ev.camera_id)
        if camera is None:
            rejected.append(RejectedEventV1(event_id=ev.event_id, reason=REASON_UNKNOWN_CAMERA))
            continue
        try:
            async with session.begin_nested():
                session.add(_to_row(ev, device, camera, received_at))
                await session.flush()
        except IntegrityError:  # concurrent insert of the same event_id
            duplicates.append(ev.event_id)
            continue
        seen_in_batch.add(ev.event_id)
        accepted.append(ev.event_id)

    device.last_seen_at = received_at
    await session.commit()
    return EventBatchResponseV1(accepted=accepted, duplicates=duplicates, rejected=rejected)
