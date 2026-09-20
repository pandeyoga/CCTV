"""Config = YAML (non-secret) + environment (secrets). Secrets never live in YAML or logs.

Env vars: EDGE_API_KEY (required for sending), EDGE_RTSP_URL (required when source.kind == rtsp).
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["file", "rtsp", "synthetic"] = "file"
    path: str | None = None
    start_ts_utc: datetime | None = None
    fps_override: float | None = None
    frame_stride: int = Field(default=1, ge=1, description="process every Nth frame (RTSP CPU budget)")
    synthetic_frames: int = 0


class LineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line_id: str = "door-1"
    ax: float
    ay: float
    bx: float
    by: float
    enter_side: Literal["left", "right"] = "left"


class CounterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hysteresis: float = 0.02
    min_confirm_frames: int = 2
    track_ttl_frames: int = 30
    anchor: Literal["bottom_center", "center"] = "bottom_center"


class DetectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["yolox_onnx", "scripted"] = "yolox_onnx"
    model_path: str | None = None
    input_size: tuple[int, int] = (640, 640)
    conf_threshold: float = 0.4
    nms_threshold: float = 0.45


class TrackerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["iou"] = "iou"
    min_iou: float = 0.3
    max_age: int = 15
    min_hits: int = 2


class StoreConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = "./edge_events.sqlite3"
    capacity: int = 50_000


class BackendConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(description="e.g. https://api.example.com (no trailing path)")
    batch_size: int = 100
    timeout_s: float = 10.0
    base_backoff_s: float = 1.0
    max_backoff_s: float = Field(default=60.0, description="upper bound of the retry delay AFTER jitter")
    heartbeat_interval_s: float = Field(default=60.0, gt=0, description="server marks the device stale after 3x this")


class EdgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: str = Field(min_length=1, description="local label only; server identity comes from the API key")
    camera_id: str = Field(min_length=1)
    source: SourceConfig
    line: LineConfig
    counter: CounterConfig = CounterConfig()
    detector: DetectorConfig = DetectorConfig()
    tracker: TrackerConfig = TrackerConfig()
    store: StoreConfig = StoreConfig()
    backend: BackendConfig | None = None
    health_file: str | None = "./edge_health.json"


class Secrets(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: str | None
    rtsp_url: str | None

    @classmethod
    def from_env(cls) -> "Secrets":
        return cls(api_key=os.environ.get("EDGE_API_KEY") or None, rtsp_url=os.environ.get("EDGE_RTSP_URL") or None)


def load_config(path: str | Path) -> EdgeConfig:
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return EdgeConfig.model_validate(raw)
