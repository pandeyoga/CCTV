"""Alert evaluation (ADR-028). Pure decision helpers + one DB pass per tenant set.

Rules (per active device unless noted), evaluated only while the store is open (ADR-026 `is_open_at`); an open alert is
resolved whenever its condition is no longer true, open or closed:
- heartbeat_lost      : last heartbeat older than `heartbeat_lost_min` (devices that never sent one are `unknown`, not alerted)
- camera_down         : latest heartbeat fresh and `source_down` for longer than `camera_down_min`
- buffer_full         : latest heartbeat fresh and `pending_events >= buffer_pending_threshold`
- no_events_open_hours: store-level; at least one connected device, store open for `no_events_min`, no count event for that long
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .hours import is_open_at
from .models import Alert, AlertRule, Camera, CountEvent, Device, DeviceHeartbeat, Store

DEFAULT_RULES = dict(heartbeat_lost_min=3, camera_down_min=2, buffer_pending_threshold=1000, no_events_min=60)
SEVERITY = {"heartbeat_lost": "critical", "camera_down": "critical", "buffer_full": "warning", "no_events_open_hours": "warning"}


@dataclass(frozen=True)
class Condition:
    rule: str
    device_id: UUID | None
    since: datetime  # when the threshold was crossed
    message: str


def rules_for(store_id: UUID, row: AlertRule | None) -> dict:
    if row is None:
        return dict(DEFAULT_RULES)
    return dict(heartbeat_lost_min=row.heartbeat_lost_min, camera_down_min=row.camera_down_min,
                buffer_pending_threshold=row.buffer_pending_threshold, no_events_min=row.no_events_min)


def device_conditions(d: Device, rules: dict, now: datetime, down_since: datetime | None) -> list[Condition]:
    """Pure: which device rules fire right now. `down_since` = first heartbeat of the current source_down run."""
    if not d.is_active or d.last_heartbeat_at is None:
        return []
    out: list[Condition] = []
    lost_after = timedelta(minutes=rules["heartbeat_lost_min"])
    if now - d.last_heartbeat_at > lost_after:
        out.append(Condition("heartbeat_lost", d.id, d.last_heartbeat_at + lost_after,
                             f"{d.name}: tidak ada heartbeat lebih dari {rules['heartbeat_lost_min']} menit"))
        return out  # a dead agent cannot report camera/buffer state
    if d.hb_source_status == "source_down" and down_since is not None:
        cam_after = timedelta(minutes=rules["camera_down_min"])
        if now - down_since > cam_after:
            out.append(Condition("camera_down", d.id, down_since + cam_after,
                                 f"{d.name}: kamera terputus lebih dari {rules['camera_down_min']} menit"))
    if (d.hb_pending_events or 0) >= rules["buffer_pending_threshold"]:
        out.append(Condition("buffer_full", d.id, now, f"{d.name}: {d.hb_pending_events} event tertunda di buffer edge (ambang {rules['buffer_pending_threshold']})"))
    return out


def store_condition(store: Store, rules: dict, now: datetime, connected: bool, has_camera: bool, last_event: datetime | None) -> Condition | None:
    """Pure: no count events while open. Requires a connected device and a camera, and the store open for the whole window."""
    n = rules["no_events_min"]
    if n is None or not connected or not has_camera:
        return None
    window = timedelta(minutes=n)
    tz = ZoneInfo(store.timezone)
    if not is_open_at(store, (now - window).astimezone(tz)):
        return None  # opened less than n minutes ago
    if last_event is not None and now - last_event <= window:
        return None
    since = (last_event + window) if last_event is not None else now
    return Condition("no_events_open_hours", None, since, f"{store.name}: tidak ada event masuk/keluar selama {n} menit pada jam buka")


async def _down_since(s: AsyncSession, device_id: UUID) -> datetime | None:
    last_ok = (await s.execute(select(func.max(DeviceHeartbeat.received_at)).where(DeviceHeartbeat.device_id == device_id, DeviceHeartbeat.source_status == "ok"))).scalar_one()
    q = select(func.min(DeviceHeartbeat.received_at)).where(DeviceHeartbeat.device_id == device_id, DeviceHeartbeat.source_status == "source_down")
    if last_ok is not None:
        q = q.where(DeviceHeartbeat.received_at > last_ok)
    return (await s.execute(q)).scalar_one()


async def evaluate(s: AsyncSession, tenant_ids, now: datetime) -> None:
    """Open/resolve alerts for every store of the given tenants. Commits."""
    stores = (await s.execute(select(Store).where(Store.tenant_id.in_(list(tenant_ids))))).scalars().all()
    if not stores:
        return
    store_ids = [st.id for st in stores]
    rule_rows = {r.store_id: r for r in (await s.execute(select(AlertRule).where(AlertRule.store_id.in_(store_ids)))).scalars()}
    open_alerts = (await s.execute(select(Alert).where(Alert.store_id.in_(store_ids), Alert.resolved_at.is_(None)))).scalars().all()
    open_by_key: dict[tuple[UUID, UUID | None, str], Alert] = {(a.store_id, a.device_id, a.rule): a for a in open_alerts}
    active: set[tuple[UUID, UUID | None, str]] = set()
    devices_by_store: dict[UUID, list[Device]] = {}
    for d in (await s.execute(select(Device).where(Device.store_id.in_(store_ids)))).scalars():
        devices_by_store.setdefault(d.store_id, []).append(d)
    cams = set((await s.execute(select(Camera.store_id).where(Camera.store_id.in_(store_ids)).distinct())).scalars())

    for st in stores:
        rules = rules_for(st.id, rule_rows.get(st.id))
        tz = ZoneInfo(st.timezone)
        open_now = is_open_at(st, now.astimezone(tz))
        conds: list[Condition] = []
        connected = False
        for d in devices_by_store.get(st.id, []):
            down_since = await _down_since(s, d.id) if (d.is_active and d.hb_source_status == "source_down") else None
            dc = device_conditions(d, rules, now, down_since)
            conds.extend(dc)
            if d.is_active and d.last_heartbeat_at is not None and not any(c.rule == "heartbeat_lost" for c in dc):
                connected = True
        last_event = (await s.execute(select(func.max(CountEvent.event_ts)).where(CountEvent.store_id == st.id))).scalar_one()
        sc = store_condition(st, rules, now, connected, st.id in cams, last_event)
        if sc:
            conds.append(sc)
        for c in conds:
            key = (st.id, c.device_id, c.rule)
            active.add(key)
            existing = open_by_key.get(key)
            if existing is not None:
                existing.last_seen_at = now
                existing.message = c.message
            elif open_now:  # new incidents only while the store is open (ADR-026)
                s.add(Alert(tenant_id=st.tenant_id, store_id=st.id, device_id=c.device_id, rule=c.rule, severity=SEVERITY[c.rule],
                            message=c.message, opened_at=max(c.since, now - timedelta(days=1)), last_seen_at=now))
    for key, a in open_by_key.items():
        if key not in active:
            a.resolved_at = now
    await s.commit()
