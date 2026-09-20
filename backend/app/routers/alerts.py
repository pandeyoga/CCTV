"""Alerts (ADR-028): GET /api/v1/alerts evaluates the caller's tenants first, then lists incidents; acknowledge;
per-store alert rules (owner writes)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..alerts import DEFAULT_RULES, evaluate, rules_for
from ..auth import CurrentUser, forbidden, get_session, require_user
from ..models import Alert, AlertRule, DashboardUser, Device, Store
from ..schemas import AlertListOut, AlertOut, AlertRulesOut
from .manage import _managed_store, _visible_store

router = APIRouter(prefix="/api/v1", tags=["alerts"])

User = Annotated[CurrentUser, Depends(require_user)]
Db = Annotated[AsyncSession, Depends(get_session)]


class AlertRulesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heartbeat_lost_min: int = Field(ge=1, le=1440)
    camera_down_min: int = Field(ge=1, le=1440)
    buffer_pending_threshold: int = Field(ge=1, le=1_000_000)
    no_events_min: int | None = Field(default=None, ge=5, le=1440)


def _rules_out(store_id: UUID, row: AlertRule | None) -> AlertRulesOut:
    return AlertRulesOut(store_id=store_id, is_default=row is None, **rules_for(store_id, row))


async def _alert_out(s: AsyncSession, rows: list[Alert]) -> list[AlertOut]:
    if not rows:
        return []
    stores = {st.id: st for st in (await s.execute(select(Store).where(Store.id.in_({a.store_id for a in rows})))).scalars()}
    dev_ids = {a.device_id for a in rows if a.device_id}
    devices = {d.id: d for d in (await s.execute(select(Device).where(Device.id.in_(dev_ids)))).scalars()} if dev_ids else {}
    user_ids = {a.acknowledged_by for a in rows if a.acknowledged_by}
    users = {u.id: u for u in (await s.execute(select(DashboardUser).where(DashboardUser.id.in_(user_ids)))).scalars()} if user_ids else {}
    return [AlertOut(alert_id=a.id, tenant_id=a.tenant_id, store_id=a.store_id, store_name=stores[a.store_id].name,
                     store_timezone=stores[a.store_id].timezone, device_id=a.device_id,
                     device_name=devices[a.device_id].name if a.device_id in devices else None, rule=a.rule, severity=a.severity,
                     message=a.message, opened_at=a.opened_at, last_seen_at=a.last_seen_at, resolved_at=a.resolved_at,
                     acknowledged_at=a.acknowledged_at,
                     acknowledged_by_email=users[a.acknowledged_by].email if a.acknowledged_by in users else None) for a in rows]


@router.get("/alerts", response_model=AlertListOut)
async def list_alerts(s: Db, user: User, status_: Annotated[Literal["open", "resolved", "all"], Query(alias="status")] = "open",
                      store_id: UUID | None = None, limit: Annotated[int, Query(ge=1, le=500)] = 100) -> AlertListOut:
    now = datetime.now(timezone.utc)
    if not user.tenant_ids:
        return AlertListOut(evaluated_at=now, open_count=0, unacknowledged_count=0, alerts=[])
    await evaluate(s, user.tenant_ids, now)
    base = select(Alert).where(Alert.tenant_id.in_(user.tenant_ids))
    if store_id is not None:
        await _visible_store(s, store_id, user)
        base = base.where(Alert.store_id == store_id)
    open_rows = (await s.execute(base.where(Alert.resolved_at.is_(None)))).scalars().all()
    q = base
    if status_ == "open":
        q = q.where(Alert.resolved_at.is_(None))
    elif status_ == "resolved":
        q = q.where(Alert.resolved_at.is_not(None))
    rows = (await s.execute(q.order_by(Alert.resolved_at.is_not(None), Alert.opened_at.desc()).limit(limit))).scalars().all()
    return AlertListOut(evaluated_at=now, open_count=len(open_rows),
                        unacknowledged_count=sum(1 for a in open_rows if a.acknowledged_at is None), alerts=await _alert_out(s, list(rows)))


@router.post("/alerts/{alert_id}/ack", response_model=AlertOut)
async def acknowledge(alert_id: UUID, s: Db, user: User) -> AlertOut:
    a = await s.get(Alert, alert_id)
    if a is None or a.tenant_id not in user.tenant_ids:
        raise HTTPException(404, "alert not found")
    if not user.can_manage(a.tenant_id):
        raise forbidden("Owner role required to acknowledge alerts")
    if a.acknowledged_at is None:
        a.acknowledged_at = datetime.now(timezone.utc)
        a.acknowledged_by = user.user_id
        await s.commit()
    return (await _alert_out(s, [a]))[0]


@router.get("/stores/{store_id}/alert-rules", response_model=AlertRulesOut)
async def get_rules(store_id: UUID, s: Db, user: User) -> AlertRulesOut:
    st = await _visible_store(s, store_id, user)
    return _rules_out(st.id, await s.get(AlertRule, st.id))


@router.put("/stores/{store_id}/alert-rules", response_model=AlertRulesOut)
async def put_rules(store_id: UUID, body: AlertRulesIn, s: Db, user: User) -> AlertRulesOut:
    st = await _managed_store(s, store_id, user)
    row = await s.get(AlertRule, st.id)
    if row is None:
        row = AlertRule(store_id=st.id, tenant_id=st.tenant_id, **DEFAULT_RULES)
        s.add(row)
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    await s.commit()
    return _rules_out(st.id, row)


@router.delete("/stores/{store_id}/alert-rules", response_model=AlertRulesOut)
async def reset_rules(store_id: UUID, s: Db, user: User) -> AlertRulesOut:
    st = await _managed_store(s, store_id, user)
    row = await s.get(AlertRule, st.id)
    if row is not None:
        await s.delete(row)
        await s.commit()
    return _rules_out(st.id, None)
