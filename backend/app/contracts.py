"""Backend copy of the edge->backend contract. MUST stay identical to edge_agent/edge_agent/contracts.py.

Guarded by tests/test_contract_drift.py against /contracts/event_v1.schema.json (ADR-002).
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
