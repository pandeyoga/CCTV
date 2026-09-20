"""Dashboard read models (shapes fixed in docs/CONTRACTS.md)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StoreOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    store_id: UUID
    tenant_id: UUID
    name: str
    timezone: str
    open_time: str | None = None  # "HH:MM" store-local; both None => open 24 h (ADR-026)
    close_time: str | None = None


class SummaryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    store_id: UUID
    date: date
    timezone: str
    enter: int
    exit: int
    occupancy_estimate: int
    last_event_at: datetime | None


class HourBucket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hour_start: datetime  # store-local, tz-aware
    enter: int
    exit: int


class HourlyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    store_id: UUID
    date: date
    timezone: str
    buckets: list[HourBucket]


class DeviceOut(BaseModel):
    """Liveness is derived from heartbeats only; last_event_at is visitor activity, not health."""

    model_config = ConfigDict(extra="forbid")
    device_id: UUID
    name: str
    is_active: bool
    last_event_at: datetime | None  # server receive time of the last accepted event batch
    last_heartbeat_at: datetime | None  # server receive time of the last heartbeat; None => status unknown
    source_status: str | None  # "ok" | "source_down" from the last heartbeat
    last_frame_age_s: float | None
    pending_events: int | None
    agent_version: str | None


class DeviceWithStoreOut(DeviceOut):
    """Cross-store device list (GET /api/v1/devices): DeviceOut plus the store it belongs to."""

    store_id: UUID
    store_name: str
    store_timezone: str


# ----------------------------------------------------------------------------- reports (ADR-025)
class DayBucket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date  # store-local calendar day
    enter: int
    exit: int


class RangeTotals(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_date: date
    to_date: date
    days: int
    enter: int
    exit: int


class HourProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hour: int  # 0..23 store-local
    enter: int
    exit: int


class RangeReportOut(BaseModel):
    """Daily totals for [from, to] in the store timezone, the immediately preceding period of equal length,
    and the hour-of-day profile summed over the range (for "busiest hours")."""

    model_config = ConfigDict(extra="forbid")
    store_id: UUID
    timezone: str
    open_time: str | None
    close_time: str | None
    outside_hours_excluded: int  # events in the current range that fell outside opening hours and were not counted
    current: RangeTotals
    previous: RangeTotals
    daily: list[DayBucket]
    hourly_profile: list[HourProfile]


class StoreOverviewOut(BaseModel):
    """One row per permitted store for the multi-store table. `date` is today in each store's own timezone."""

    model_config = ConfigDict(extra="forbid")
    store_id: UUID
    tenant_id: UUID
    name: str
    timezone: str
    date: date
    enter: int
    exit: int
    yesterday_enter: int
    avg_enter_7d: float  # mean daily enter over the 7 days before today
    last_event_at: datetime | None
    devices_total: int
    devices_problem: int  # inactive excluded; stale (>180 s) or camera_down or never heartbeat; always 0 while the store is closed
    is_open_now: bool
    open_time: str | None
    close_time: str | None


# ----------------------------------------------------------------------------- heartbeat history (ADR-027)
HeartbeatState = Literal["connected", "camera_down", "stale", "unknown"]


class HeartbeatSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: datetime  # UTC
    end: datetime  # UTC (exclusive)
    status: HeartbeatState


class HeartbeatHistoryOut(BaseModel):
    """Up/down timeline of one device over [from, to]: consecutive heartbeats ≤ stale threshold apart form a
    connected/camera_down segment; larger gaps are `stale`; time before the first sample in the window is `unknown`."""

    model_config = ConfigDict(extra="forbid")
    device_id: UUID
    from_ts: datetime
    to_ts: datetime
    stale_after_s: int
    samples: int
    uptime_pct: float  # share of the window in `connected` (camera_down counts as down)
    segments: list[HeartbeatSegment]


# ----------------------------------------------------------------------------- alerts (ADR-028)
AlertRuleName = Literal["heartbeat_lost", "camera_down", "buffer_full", "no_events_open_hours"]


class AlertRulesOut(BaseModel):
    """Per-store thresholds; `is_default` is true while the store has no saved row."""

    model_config = ConfigDict(extra="forbid")
    store_id: UUID
    heartbeat_lost_min: int
    camera_down_min: int
    buffer_pending_threshold: int
    no_events_min: int | None  # None = rule off
    is_default: bool


class AlertOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alert_id: UUID
    tenant_id: UUID
    store_id: UUID
    store_name: str
    store_timezone: str
    device_id: UUID | None
    device_name: str | None
    rule: AlertRuleName
    severity: Literal["warning", "critical"]
    message: str
    opened_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None
    acknowledged_at: datetime | None
    acknowledged_by_email: str | None


class AlertListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluated_at: datetime
    open_count: int
    unacknowledged_count: int  # open and not yet acknowledged (bell badge)
    alerts: list[AlertOut]


# ----------------------------------------------------------------------------- management (ADR-024)
class TenantOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: UUID
    name: str
    contact_email: str | None
    role: str  # platform_admin | owner | staff — the caller's role for this tenant
    store_count: int
    created_at: datetime


class CameraOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    camera_id: UUID
    store_id: UUID
    device_id: UUID | None
    external_id: str  # == payload camera_id
    name: str
    created_at: datetime


class DeviceKeyOut(BaseModel):
    """Returned only on device creation / key rotation. The key is never stored or shown again."""

    model_config = ConfigDict(extra="forbid")
    device: DeviceOut
    api_key_show_once: str


class MembershipOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: UUID
    tenant_name: str
    role: str


class MemberOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    email: str
    role: str
    is_active: bool
    is_platform_admin: bool
    created_at: datetime


class UserAdminOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    email: str
    is_active: bool
    is_platform_admin: bool
    created_at: datetime
    memberships: list[MembershipOut]
