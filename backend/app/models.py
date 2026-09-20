"""SQLAlchemy 2.x models. Mirror of docs/DATA_MODEL.md (the SSOT for relations)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Double, ForeignKey, Index, Integer, SmallInteger, String, Text,
    UniqueConstraint, Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """Always tz-aware UTC in Python; naive UTC on SQLite, timestamptz on PostgreSQL."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime not allowed")
        value = value.astimezone(timezone.utc)
        return value if dialect.name == "postgresql" else value.replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    contact_email: Mapped[str | None] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Store(Base):
    __tablename__ = "stores"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_stores_tenant_name"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    timezone: Mapped[str] = mapped_column(String(64))  # IANA
    open_time: Mapped[str | None] = mapped_column(String(5))  # "HH:MM" store-local; NULL with close_time => open 24 h (ADR-026)
    close_time: Mapped[str | None] = mapped_column(String(5))
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64))  # Telegram group/chat for alert messages (ADR-029); NULL = off
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stores.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    key_id: Mapped[str] = mapped_column(String(32), unique=True)  # public part of dk_<key_id>.<secret>
    secret_hash: Mapped[str] = mapped_column(String(64))  # sha256 hex of the secret only
    api_key_prefix: Mapped[str] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # last accepted EVENT batch (server time)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # server receive time of last heartbeat
    hb_source_status: Mapped[str | None] = mapped_column(String(16))  # ok | source_down (from last heartbeat)
    hb_last_frame_age_s: Mapped[float | None] = mapped_column(Double)
    hb_pending_events: Mapped[int | None] = mapped_column(Integer)
    hb_tracking_session_id: Mapped[int | None] = mapped_column(Integer)
    hb_agent_version: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    store: Mapped[Store] = relationship(lazy="joined")


class DeviceHeartbeat(Base):
    """One row per received heartbeat (ADR-027); pruned to HEARTBEAT_RETENTION_DAYS per device on insert."""

    __tablename__ = "device_heartbeats"
    __table_args__ = (Index("ix_device_heartbeats_device_received", "device_id", "received_at"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"))
    received_at: Mapped[datetime] = mapped_column(UTCDateTime)  # server clock
    source_status: Mapped[str] = mapped_column(String(16))  # ok | source_down
    last_frame_age_s: Mapped[float | None] = mapped_column(Double)
    pending_events: Mapped[int] = mapped_column(Integer)
    tracking_session_id: Mapped[int] = mapped_column(Integer)
    agent_version: Mapped[str] = mapped_column(String(32))


HEARTBEAT_RETENTION_DAYS = 7


class AlertRule(Base):
    """Per-store thresholds (ADR-028). One row per store, created on first PUT; stores without a row use the defaults."""

    __tablename__ = "alert_rules"
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stores.id"), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    heartbeat_lost_min: Mapped[int] = mapped_column(Integer, default=3)  # no heartbeat for > N minutes
    camera_down_min: Mapped[int] = mapped_column(Integer, default=2)  # source_down for > N minutes
    buffer_pending_threshold: Mapped[int] = mapped_column(Integer, default=1000)  # pending_events >= N
    no_events_min: Mapped[int | None] = mapped_column(Integer)  # no count event for > N minutes while open; NULL = off (no ORM default: None must persist)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


ALERT_RULES = ("heartbeat_lost", "camera_down", "buffer_full", "no_events_open_hours")


class Alert(Base):
    """One row per incident (ADR-028): opened when a rule fires, resolved when the condition clears. At most one open
    row per (store, device, rule); history is kept."""

    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_tenant_opened", "tenant_id", "opened_at"), Index("ix_alerts_store_resolved", "store_id", "resolved_at"))
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stores.id"))
    device_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("devices.id"))  # NULL for store-level rules
    rule: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(8))  # warning | critical
    message: Mapped[str] = mapped_column(String(256))
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime)  # when the condition started (threshold crossed)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)  # last evaluation that still saw the condition
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("dashboard_users.id"))
    notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # external channel delivered the "opened" message (ADR-029)
    resolved_notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class DashboardUser(Base):
    """Operator-provisioned dashboard login (email + bcrypt hash). No public signup."""

    __tablename__ = "dashboard_users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True)  # stored lower-case
    password_hash: Mapped[str] = mapped_column(String(128))  # bcrypt
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)  # sees/manages every tenant (ADR-024)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


MEMBERSHIP_ROLES = ("owner", "staff")  # owner manages the tenant; staff is read-only (ADR-024)


class TenantMembership(Base):
    """Which tenants a dashboard user may access and with which role. Authorization SSOT; never taken from requests."""

    __tablename__ = "tenant_memberships"
    __table_args__ = (UniqueConstraint("user_id", "tenant_id", name="uq_tenant_memberships_user_tenant"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dashboard_users.id"), index=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="staff")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (UniqueConstraint("store_id", "external_id", name="uq_cameras_store_external"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stores.id"), index=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("devices.id"))
    external_id: Mapped[str] = mapped_column(String(64))  # == payload camera_id
    name: Mapped[str] = mapped_column(String(128))
    snapshot_at: Mapped[datetime | None] = mapped_column(UTCDateTime)  # last JPEG uploaded by the edge (ADR-030); file on SNAPSHOT_DIR
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Zone(Base):
    """Polygon region on one camera (ADR-031). `external_id` == payload zone_id; polygon = JSON [[x,y],...] normalized."""

    __tablename__ = "zones"
    __table_args__ = (UniqueConstraint("camera_id", "external_id", name="uq_zones_camera_external"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stores.id"), index=True)
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    polygon: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ZoneSample(Base):
    """One occupancy sample per zone per interval (ADR-031). `count` at `sample_ts`, `count_max` within the interval."""

    __tablename__ = "zone_samples"
    __table_args__ = (Index("ix_zone_samples_zone_ts", "zone_id", "sample_ts"), Index("ix_zone_samples_store_ts", "store_id", "sample_ts"))
    sample_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stores.id"))
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id"))
    zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("zones.id"))
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"))
    sample_ts: Mapped[datetime] = mapped_column(UTCDateTime)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    interval_s: Mapped[float] = mapped_column(Double)
    count: Mapped[int] = mapped_column(Integer)
    count_max: Mapped[int] = mapped_column(Integer)


class CountLine(Base):
    __tablename__ = "count_lines"
    __table_args__ = (UniqueConstraint("camera_id", "external_id", name="uq_count_lines_camera_external"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(64))  # == payload line_id
    ax: Mapped[float] = mapped_column(Double)
    ay: Mapped[float] = mapped_column(Double)
    bx: Mapped[float] = mapped_column(Double)
    by: Mapped[float] = mapped_column(Double)
    enter_side: Mapped[str] = mapped_column(String(5))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class CountEvent(Base):
    __tablename__ = "count_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('enter','exit')", name="ck_count_events_type"),
        Index("ix_count_events_store_ts", "store_id", "event_ts"),
        Index("ix_count_events_camera_ts", "camera_id", "event_ts"),
        Index("ix_count_events_tenant_ts", "tenant_id", "event_ts"),
    )
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)  # client-generated idempotency key
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    store_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stores.id"))
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id"))
    camera_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cameras.id"))
    line_id: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(8))
    event_ts: Mapped[datetime] = mapped_column(UTCDateTime)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    track_id: Mapped[int] = mapped_column(Integer)
    frame_index: Mapped[int] = mapped_column(Integer)
    source_kind: Mapped[str] = mapped_column(String(16))
    schema_version: Mapped[int] = mapped_column(SmallInteger)
    tracking_session_id: Mapped[int | None] = mapped_column(Integer)  # track_id is unique only within it
    raw_error: Mapped[str | None] = mapped_column(Text)  # reserved; unused in v1
