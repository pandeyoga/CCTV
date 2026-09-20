"""Backend copy of the edge<->backend contract. MUST stay identical to edge_agent/edge_agent/contracts.py.

Guarded by tests/test_contract_drift.py against /contracts/*.schema.json (ADR-002).
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = 1
MAX_BATCH_SIZE = 500


class EventType(str, Enum):
    ENTER = "enter"
    EXIT = "exit"


SourceKind = Literal["file", "rtsp", "synthetic"]


class CountEventV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = SCHEMA_VERSION
    event_id: UUID = Field(description="Client-generated UUID4; stable across retries; server dedup key")
    event_type: EventType
    event_ts: datetime = Field(description="When the crossing happened (UTC, tz-aware). Not the server receive time.")
    camera_id: str = Field(min_length=1, max_length=64)
    line_id: str = Field(min_length=1, max_length=64)
    track_id: int = Field(ge=0, description="Local tracker id; NOT a person identity")
    frame_index: int = Field(ge=0)
    source_kind: SourceKind
    tracking_session_id: int | None = Field(
        default=None, ge=0,
        description="Edge tracking session (increments on stream reconnect); track_id is only unique within it. "
                    "Optional for v1 backward compatibility.",
    )

    @field_validator("event_ts")
    @classmethod
    def _must_be_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("event_ts must be timezone-aware UTC")
        return v.astimezone(timezone.utc)


class EventBatchRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[CountEventV1] = Field(min_length=1, max_length=MAX_BATCH_SIZE)


class RejectedEventV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    reason: str


class EventBatchResponseV1(BaseModel):
    """Server acknowledgment. accepted + duplicates are both 'safe to mark sent'."""

    model_config = ConfigDict(extra="forbid")
    accepted: list[UUID] = Field(default_factory=list)
    duplicates: list[UUID] = Field(default_factory=list)
    rejected: list[RejectedEventV1] = Field(default_factory=list)


SourceStatus = Literal["ok", "source_down"]


class HeartbeatV1(BaseModel):
    """Device liveness, independent of visitor events. Identity comes from device auth; the server
    stamps `received_at` itself (edge clocks are informational only)."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = SCHEMA_VERSION
    sent_at: datetime = Field(description="Edge wall clock (UTC, tz-aware); informational")
    source_status: SourceStatus
    last_frame_age_s: float | None = Field(default=None, ge=0, description="Seconds since the last processed frame; null before the first frame")
    pending_events: int = Field(ge=0, description="Events buffered locally, not yet acknowledged")
    frames_processed: int = Field(ge=0)
    tracking_session_id: int = Field(ge=0)
    agent_version: str = Field(min_length=1, max_length=32)

    @field_validator("sent_at")
    @classmethod
    def _sent_at_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("sent_at must be timezone-aware UTC")
        return v.astimezone(timezone.utc)


class HeartbeatAckV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    received_at: datetime


# ----------------------------------------------------------------------------- zone samples (ADR-031)
class ZoneSampleV1(BaseModel):
    """Occupancy of one zone over one sampling interval. `count` = tracks inside the zone at `sample_ts`;
    `count_max` = maximum simultaneous tracks inside during the interval ending at `sample_ts`.
    Not durable on the edge (bounded memory queue) — telemetry, not accounting."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = SCHEMA_VERSION
    sample_id: UUID = Field(description="Client-generated UUID4; server dedup key")
    camera_id: str = Field(min_length=1, max_length=64)
    zone_id: str = Field(min_length=1, max_length=64, description="External zone id configured on the camera")
    sample_ts: datetime = Field(description="End of the interval (UTC, tz-aware)")
    interval_s: float = Field(gt=0, le=3600)
    count: int = Field(ge=0)
    count_max: int = Field(ge=0)

    @field_validator("sample_ts")
    @classmethod
    def _ts_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("sample_ts must be timezone-aware UTC")
        return v.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _max_ge_count(self) -> "ZoneSampleV1":
        if self.count_max < self.count:
            raise ValueError("count_max must be >= count")
        return self


class ZoneSampleBatchRequestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    samples: list[ZoneSampleV1] = Field(min_length=1, max_length=MAX_BATCH_SIZE)


class RejectedSampleV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_id: UUID
    reason: str


class ZoneSampleBatchResponseV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: list[UUID] = Field(default_factory=list)
    duplicates: list[UUID] = Field(default_factory=list)
    rejected: list[RejectedSampleV1] = Field(default_factory=list)


# ----------------------------------------------------------------------------- server -> edge config (ADR-030)
EnterSide = Literal["left", "right"]
Point = tuple[float, float]


class LineV1(BaseModel):
    """Counting line in normalized coordinates (0..1, origin top-left, y down); direction a->b; `enter_side` relative to it."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    line_id: str = Field(min_length=1, max_length=64)
    ax: float = Field(ge=0, le=1)
    ay: float = Field(ge=0, le=1)
    bx: float = Field(ge=0, le=1)
    by: float = Field(ge=0, le=1)
    enter_side: EnterSide

    @model_validator(mode="after")
    def _distinct(self) -> "LineV1":
        if (self.ax, self.ay) == (self.bx, self.by):
            raise ValueError("line endpoints must differ")
        return self


class ZoneV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    zone_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    polygon: list[Point] = Field(min_length=3, max_length=64, description="Normalized vertices, closed implicitly")

    @field_validator("polygon")
    @classmethod
    def _in_unit_square(cls, v: list[Point]) -> list[Point]:
        for x, y in v:
            if not (0 <= x <= 1 and 0 <= y <= 1):
                raise ValueError("polygon vertices must be within 0..1")
        return v


class CameraConfigV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    camera_id: str = Field(min_length=1, max_length=64)
    lines: list[LineV1] = Field(default_factory=list)
    zones: list[ZoneV1] = Field(default_factory=list)


class DeviceConfigV1(BaseModel):
    """GET /api/v1/devices/me/config. `config_version` changes whenever any line/zone of the device's cameras changes;
    the edge reloads without restart when it differs from the last applied version."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = SCHEMA_VERSION
    config_version: str = Field(min_length=1, max_length=64)
    generated_at: datetime
    cameras: list[CameraConfigV1]


def event_batch_json_schema() -> dict:
    return {
        "request": EventBatchRequestV1.model_json_schema(),
        "response": EventBatchResponseV1.model_json_schema(),
    }


def heartbeat_json_schema() -> dict:
    return {
        "request": HeartbeatV1.model_json_schema(),
        "response": HeartbeatAckV1.model_json_schema(),
    }


def zone_sample_json_schema() -> dict:
    return {
        "request": ZoneSampleBatchRequestV1.model_json_schema(),
        "response": ZoneSampleBatchResponseV1.model_json_schema(),
    }


def device_config_json_schema() -> dict:
    return {"response": DeviceConfigV1.model_json_schema()}
