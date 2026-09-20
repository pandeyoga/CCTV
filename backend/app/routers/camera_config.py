"""Server-side camera geometry + snapshots (ADR-030).

Edge (device key):  GET  /api/v1/devices/me/config          — lines + zones of the cameras this device may process
                    POST /api/v1/devices/snapshot?camera_id= — raw JPEG body, one file per camera (overwritten)
Dashboard (JWT):    GET/PUT/DELETE /api/v1/cameras/{id}/lines[/{line_id}], GET /api/v1/cameras/{id}/snapshot,
                    GET/POST /api/v1/cameras/{id}/zones, PATCH/DELETE /api/v1/zones/{id}
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path as FsPath
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import CurrentUser, get_session, require_device, require_user
from ..contracts import CameraConfigV1, DeviceConfigV1, EnterSide, LineV1, Point, ZoneV1
from ..models import Camera, CountLine, Device, Zone, ZoneSample
from ..schemas import LineOut, SnapshotAckOut, ZoneOut
from .manage import _managed_camera, _visible_store

router = APIRouter(prefix="/api/v1", tags=["camera-config"])

User = Annotated[CurrentUser, Depends(require_user)]
Db = Annotated[AsyncSession, Depends(get_session)]
Dev = Annotated[Device, Depends(require_device)]
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
LINE_ID = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")


class LineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ax: float = Field(ge=0, le=1)
    ay: float = Field(ge=0, le=1)
    bx: float = Field(ge=0, le=1)
    by: float = Field(ge=0, le=1)
    enter_side: EnterSide


class ZoneIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_id: str = LINE_ID
    name: str = Field(min_length=1, max_length=128)
    polygon: list[Point] = Field(min_length=3, max_length=64)

    _poly = field_validator("polygon")(lambda cls, v: ZoneV1(zone_id="x", name="x", polygon=v).polygon)


class ZonePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=128)
    polygon: list[Point] | None = Field(default=None, min_length=3, max_length=64)

    _poly = field_validator("polygon")(lambda cls, v: ZoneV1(zone_id="x", name="x", polygon=v).polygon if v is not None else v)


def _line_v1(l: CountLine) -> LineV1:
    return LineV1(line_id=l.external_id, ax=l.ax, ay=l.ay, bx=l.bx, by=l.by, enter_side=l.enter_side)


def _line_out(l: CountLine) -> LineOut:
    return LineOut(camera_id=l.camera_id, **_line_v1(l).model_dump())


def _zone_v1(z: Zone) -> ZoneV1:
    return ZoneV1(zone_id=z.external_id, name=z.name, polygon=json.loads(z.polygon))


def _zone_out(z: Zone, cam_ext: str, last: tuple[datetime, int, int] | None = None) -> ZoneOut:
    return ZoneOut(zone_id=z.id, store_id=z.store_id, camera_id=z.camera_id, camera_external_id=cam_ext, external_id=z.external_id,
                   name=z.name, polygon=json.loads(z.polygon), created_at=z.created_at,
                   last_sample_ts=last[0] if last else None, last_count=last[1] if last else None, last_count_max=last[2] if last else None)


async def _visible_camera(s: AsyncSession, camera_id: UUID, user: CurrentUser) -> Camera:
    c = await s.get(Camera, camera_id)
    if c is None or c.tenant_id not in user.tenant_ids:
        raise HTTPException(404, "camera not found")
    return c


def _snapshot_path(request: Request, camera_id: UUID) -> FsPath:
    return FsPath(request.app.state.settings.snapshot_dir) / f"{camera_id}.jpg"


# ----------------------------------------------------------------------------- edge
async def build_device_config(s: AsyncSession, device: Device) -> DeviceConfigV1:
    cams = (await s.execute(select(Camera).where(Camera.store_id == device.store_id,
                                                  (Camera.device_id == device.id) | (Camera.device_id.is_(None))).order_by(Camera.created_at))).scalars().all()
    cam_ids = [c.id for c in cams]
    lines = (await s.execute(select(CountLine).where(CountLine.camera_id.in_(cam_ids)).order_by(CountLine.created_at))).scalars().all() if cam_ids else []
    zones = (await s.execute(select(Zone).where(Zone.camera_id.in_(cam_ids)).order_by(Zone.created_at))).scalars().all() if cam_ids else []
    out = [CameraConfigV1(camera_id=c.external_id, lines=[_line_v1(l) for l in lines if l.camera_id == c.id],
                          zones=[_zone_v1(z) for z in zones if z.camera_id == c.id]) for c in cams]
    digest = hashlib.sha256(json.dumps([c.model_dump() for c in out], sort_keys=True).encode()).hexdigest()[:16]
    return DeviceConfigV1(config_version=digest, generated_at=datetime.now(timezone.utc), cameras=out)


@router.get("/devices/me/config", response_model=DeviceConfigV1)
async def device_config(s: Db, device: Dev) -> DeviceConfigV1:
    return await build_device_config(s, device)


@router.post("/devices/snapshot", response_model=SnapshotAckOut)
async def upload_snapshot(request: Request, camera_id: str, s: Db, device: Dev) -> SnapshotAckOut:
    cam = (await s.execute(select(Camera).where(Camera.store_id == device.store_id, Camera.external_id == camera_id))).scalar_one_or_none()
    if cam is None or (cam.device_id is not None and cam.device_id != device.id):
        raise HTTPException(404, "unknown camera")
    body = await request.body()
    if len(body) > MAX_SNAPSHOT_BYTES:
        raise HTTPException(413, f"snapshot larger than {MAX_SNAPSHOT_BYTES} bytes")
    if len(body) < 4 or body[:3] != b"\xff\xd8\xff":
        raise HTTPException(415, "body must be a JPEG image")
    path = _snapshot_path(request, cam.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(body)
    tmp.replace(path)
    cam.snapshot_at = datetime.now(timezone.utc)
    await s.commit()
    return SnapshotAckOut(camera_id=cam.external_id, snapshot_at=cam.snapshot_at, bytes=len(body))


# ----------------------------------------------------------------------------- dashboard: snapshot + lines
@router.get("/cameras/{camera_id}/snapshot")
async def get_snapshot(camera_id: UUID, request: Request, s: Db, user: User) -> Response:
    c = await _visible_camera(s, camera_id, user)
    path = _snapshot_path(request, c.id)
    if c.snapshot_at is None or not path.exists():
        raise HTTPException(404, "no snapshot uploaded yet")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/cameras/{camera_id}/lines", response_model=list[LineOut])
async def list_lines(camera_id: UUID, s: Db, user: User) -> list[LineOut]:
    c = await _visible_camera(s, camera_id, user)
    rows = (await s.execute(select(CountLine).where(CountLine.camera_id == c.id).order_by(CountLine.created_at))).scalars()
    return [_line_out(l) for l in rows]


@router.put("/cameras/{camera_id}/lines/{line_id}", response_model=LineOut)
async def put_line(camera_id: UUID, line_id: Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")], body: LineIn, s: Db, user: User) -> LineOut:
    c = await _managed_camera(s, camera_id, user)
    try:
        LineV1(line_id=line_id, **body.model_dump())  # shared validation: id pattern + distinct endpoints
    except ValueError as exc:
        raise HTTPException(422, str(exc.errors()[0]["msg"]) if hasattr(exc, "errors") else str(exc))
    row = (await s.execute(select(CountLine).where(CountLine.camera_id == c.id, CountLine.external_id == line_id))).scalar_one_or_none()
    if row is None:
        row = CountLine(tenant_id=c.tenant_id, camera_id=c.id, external_id=line_id)
        s.add(row)
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    await s.commit()
    return _line_out(row)


@router.delete("/cameras/{camera_id}/lines/{line_id}", status_code=204)
async def delete_line(camera_id: UUID, line_id: str, s: Db, user: User) -> Response:
    c = await _managed_camera(s, camera_id, user)
    row = (await s.execute(select(CountLine).where(CountLine.camera_id == c.id, CountLine.external_id == line_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "line not found")
    await s.delete(row)
    await s.commit()
    return Response(status_code=204)


# ----------------------------------------------------------------------------- dashboard: zones (ADR-031)
async def _last_samples(s: AsyncSession, zone_ids: list[UUID]) -> dict[UUID, tuple[datetime, int, int]]:
    if not zone_ids:
        return {}
    latest = select(ZoneSample.zone_id, func.max(ZoneSample.sample_ts).label("ts")).where(ZoneSample.zone_id.in_(zone_ids)).group_by(ZoneSample.zone_id).subquery()
    rows = await s.execute(select(ZoneSample.zone_id, ZoneSample.sample_ts, ZoneSample.count, ZoneSample.count_max)
                           .join(latest, (ZoneSample.zone_id == latest.c.zone_id) & (ZoneSample.sample_ts == latest.c.ts)))
    return {zid: (ts, c, m) for zid, ts, c, m in rows.all()}


async def zones_out(s: AsyncSession, zones: list[Zone]) -> list[ZoneOut]:
    cams = {c.id: c.external_id for c in (await s.execute(select(Camera).where(Camera.id.in_({z.camera_id for z in zones})))).scalars()} if zones else {}
    last = await _last_samples(s, [z.id for z in zones])
    return [_zone_out(z, cams[z.camera_id], last.get(z.id)) for z in zones]


@router.get("/stores/{store_id}/zones", response_model=list[ZoneOut])
async def list_store_zones(store_id: UUID, s: Db, user: User) -> list[ZoneOut]:
    st = await _visible_store(s, store_id, user)
    rows = (await s.execute(select(Zone).where(Zone.store_id == st.id).order_by(Zone.created_at))).scalars().all()
    return await zones_out(s, list(rows))


@router.get("/cameras/{camera_id}/zones", response_model=list[ZoneOut])
async def list_camera_zones(camera_id: UUID, s: Db, user: User) -> list[ZoneOut]:
    c = await _visible_camera(s, camera_id, user)
    rows = (await s.execute(select(Zone).where(Zone.camera_id == c.id).order_by(Zone.created_at))).scalars().all()
    return await zones_out(s, list(rows))


@router.post("/cameras/{camera_id}/zones", response_model=ZoneOut, status_code=201)
async def create_zone(camera_id: UUID, body: ZoneIn, s: Db, user: User) -> ZoneOut:
    c = await _managed_camera(s, camera_id, user)
    if (await s.execute(select(Zone.id).where(Zone.camera_id == c.id, Zone.external_id == body.external_id))).first():
        raise HTTPException(409, "zone_id already exists on this camera")
    z = Zone(tenant_id=c.tenant_id, store_id=c.store_id, camera_id=c.id, external_id=body.external_id, name=body.name, polygon=json.dumps(body.polygon))
    s.add(z)
    await s.commit()
    return _zone_out(z, c.external_id)


@router.patch("/zones/{zone_id}", response_model=ZoneOut)
async def patch_zone(zone_id: UUID, body: ZonePatch, s: Db, user: User) -> ZoneOut:
    z = await s.get(Zone, zone_id)
    if z is None or z.tenant_id not in user.tenant_ids:
        raise HTTPException(404, "zone not found")
    c = await _managed_camera(s, z.camera_id, user)
    if body.name is not None:
        z.name = body.name
    if body.polygon is not None:
        z.polygon = json.dumps(body.polygon)
    await s.commit()
    return _zone_out(z, c.external_id, (await _last_samples(s, [z.id])).get(z.id))


@router.delete("/zones/{zone_id}", status_code=204)
async def delete_zone(zone_id: UUID, s: Db, user: User) -> Response:
    """Deletes the zone and its samples (telemetry, not accounting — ADR-031)."""
    z = await s.get(Zone, zone_id)
    if z is None or z.tenant_id not in user.tenant_ids:
        raise HTTPException(404, "zone not found")
    await _managed_camera(s, z.camera_id, user)
    await s.execute(delete(ZoneSample).where(ZoneSample.zone_id == z.id))
    await s.delete(z)
    await s.commit()
    return Response(status_code=204)
