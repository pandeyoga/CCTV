"""QA verification tests for edge_agent Stage 1. Independent of built-in tests.

Covers each verification point listed in the review request.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest

from edge_agent.contracts import (
    CountEventV1,
    EventBatchResponseV1,
    EventType,
    event_batch_json_schema,
)
from edge_agent.counting import CrossingCounter, DirectedLine
from edge_agent.detection import ScriptedDetector
from edge_agent.health import HealthState, HealthStatus
from edge_agent.pipeline import CounterPipeline, PipelineIdentity
from edge_agent.storage import EventStore
from edge_agent.storage.event_store import BufferFullError
from edge_agent.tracking import IouTracker
from edge_agent.transport import EventSender
from edge_agent.transport.sender import SendOutcome
from edge_agent.video import SyntheticSource
from edge_agent.video.rtsp_source import RtspVideoSource

from helpers import det, track, walk

LINE = DirectedLine("door", 0.1, 0.5, 0.9, 0.5, enter_side="left")
T0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# CrossingCounter direct tests
# ---------------------------------------------------------------------------
class TestCrossingCounter:
    def _counter(self):
        return CrossingCounter(LINE, hysteresis=0.02, min_confirm_frames=2)

    def test_enter_direction_y09_to_y01(self):
        c = self._counter()
        events = []
        for i, y in enumerate(walk(0.9, 0.1, 20)):
            events += c.update([track(1, 0.5, y)], i)
        assert [e.event_type for e in events] == [EventType.ENTER]

    def test_exit_reverse_direction(self):
        c = self._counter()
        events = []
        for i, y in enumerate(walk(0.1, 0.9, 20)):
            events += c.update([track(1, 0.5, y)], i)
        assert [e.event_type for e in events] == [EventType.EXIT]

    def test_oscillation_within_hysteresis_produces_no_events(self):
        c = self._counter()
        events = []
        # oscillate between 0.505 and 0.495 (|d| = 0.005 < hysteresis 0.02)
        ys = [0.505, 0.495] * 15
        for i, y in enumerate(ys):
            events += c.update([track(1, 0.5, y)], i)
        assert events == []

    def test_new_track_on_opposite_side_produces_no_event(self):
        # Track appears already on left side (y < 0.5) — no prior confirmed side.
        c = self._counter()
        events = []
        for i, y in enumerate(walk(0.1, 0.05, 10)):
            events += c.update([track(7, 0.5, y)], i)
        assert events == []

    def test_exit_then_reenter_same_id(self):
        c = self._counter()
        seen = []
        # First go y=0.1 -> 0.9 (EXIT)
        for i, y in enumerate(walk(0.1, 0.9, 20)):
            seen += c.update([track(1, 0.5, y)], i)
        # Then y=0.9 -> 0.1 (ENTER)
        for j, y in enumerate(walk(0.9, 0.1, 20), start=20):
            seen += c.update([track(1, 0.5, y)], j)
        assert [e.event_type for e in seen] == [EventType.EXIT, EventType.ENTER]


# ---------------------------------------------------------------------------
# EventStore tests
# ---------------------------------------------------------------------------
def _mk_event(**overrides) -> CountEventV1:
    base = dict(
        event_id=uuid4(),
        event_type=EventType.ENTER,
        event_ts=T0,
        camera_id="cam-1",
        line_id="door",
        track_id=1,
        frame_index=0,
        source_kind="synthetic",
    )
    base.update(overrides)
    return CountEventV1(**base)


class TestEventStore:
    def test_append_persists_and_survives_reopen(self, tmp_path):
        db = tmp_path / "e.db"
        store = EventStore(db, capacity=10)
        ev = _mk_event()
        store.append(ev)
        assert store.counts().pending == 1
        store.close()
        store2 = EventStore(db, capacity=10)
        assert store2.counts().pending == 1
        assert store2.status_of(ev.event_id) == "pending"

    def test_duplicate_event_id_raises(self, tmp_path):
        store = EventStore(tmp_path / "e.db", capacity=10)
        ev = _mk_event()
        store.append(ev)
        # Same event_id (different payload) must raise (PK conflict)
        dup = _mk_event(event_id=ev.event_id, track_id=2)
        with pytest.raises(Exception):
            store.append(dup)

    def test_capacity_full_raises_and_pending_unchanged(self, tmp_path):
        store = EventStore(tmp_path / "e.db", capacity=2)
        e1 = _mk_event()
        e2 = _mk_event()
        store.append(e1)
        store.append(e2)
        assert store.counts().pending == 2
        with pytest.raises(BufferFullError):
            store.append(_mk_event())
        assert store.counts().pending == 2

    def test_mark_sent_frees_capacity(self, tmp_path):
        store = EventStore(tmp_path / "e.db", capacity=2)
        e1 = _mk_event()
        e2 = _mk_event()
        store.append(e1)
        store.append(e2)
        store.mark_sent([e1.event_id])
        assert store.counts().pending == 1
        assert store.counts().sent == 1
        # Now capacity has room again
        store.append(_mk_event())
        assert store.counts().pending == 2


# ---------------------------------------------------------------------------
# EventSender tests using httpx.MockTransport
# ---------------------------------------------------------------------------
class _Scripted:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []  # list of dicts: {json_body, auth_header}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(
            {
                "json": json.loads(request.content.decode("utf-8")),
                "auth": request.headers.get("Authorization"),
            }
        )
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_sender_retry_then_success_same_event_id(tmp_path, caplog):
    store = EventStore(tmp_path / "e.db", capacity=10)
    ev = _mk_event()
    store.append(ev)

    ack = EventBatchResponseV1(accepted=[ev.event_id]).model_dump(mode="json")
    scripted = _Scripted(
        [
            httpx.ConnectError("boom"),
            httpx.Response(503, json={"detail": "unavailable"}),
            httpx.Response(200, json=ack),
        ]
    )
    client = httpx.Client(transport=httpx.MockTransport(scripted))
    health = HealthState()
    secret_key = "sk-supersecret-abc123"
    sender = EventSender(
        store,
        "https://api.example.com",
        secret_key,
        health,
        client=client,
        sleep=lambda d: None,
        rng=lambda: 0.5,
    )

    with caplog.at_level(logging.DEBUG):
        r1 = sender.send_once()
        r2 = sender.send_once()
        r3 = sender.send_once()

    assert r1.outcome is SendOutcome.RETRY
    assert r2.outcome is SendOutcome.RETRY
    assert r3.outcome is SendOutcome.SENT

    # Same event_id posted every time
    posted_ids = [call["json"]["events"][0]["event_id"] for call in scripted.calls]
    assert posted_ids == [str(ev.event_id)] * 3

    # Only marked sent after 200 ack
    assert store.status_of(ev.event_id) == "sent"
    assert store.counts().pending == 0

    # API key never in captured logs
    assert secret_key not in caplog.text


def test_sender_401_marks_auth_failed_row_pending(tmp_path):
    store = EventStore(tmp_path / "e.db", capacity=10)
    ev = _mk_event()
    store.append(ev)
    scripted = _Scripted([httpx.Response(401, json={"detail": "no"})])
    client = httpx.Client(transport=httpx.MockTransport(scripted))
    health = HealthState()
    sender = EventSender(
        store,
        "https://api.example.com",
        "sk-x",
        health,
        client=client,
        sleep=lambda d: None,
        rng=lambda: 0.5,
    )
    r = sender.send_once()
    assert r.outcome is SendOutcome.AUTH_FAILED
    assert health.overall() is HealthStatus.AUTH_FAILED
    assert store.status_of(ev.event_id) == "pending"


def test_sender_duplicates_treated_as_sent(tmp_path):
    store = EventStore(tmp_path / "e.db", capacity=10)
    ev = _mk_event()
    store.append(ev)
    ack = EventBatchResponseV1(duplicates=[ev.event_id]).model_dump(mode="json")
    scripted = _Scripted([httpx.Response(200, json=ack)])
    client = httpx.Client(transport=httpx.MockTransport(scripted))
    sender = EventSender(
        store,
        "https://api.example.com",
        "sk-x",
        HealthState(),
        client=client,
        sleep=lambda d: None,
        rng=lambda: 0.5,
    )
    r = sender.send_once()
    assert r.outcome is SendOutcome.SENT
    assert r.duplicates == 1
    assert store.status_of(ev.event_id) == "sent"


# ---------------------------------------------------------------------------
# Pipeline end-to-end
# ---------------------------------------------------------------------------
def _build_pipeline(tmp_path, script, n_frames, capacity=100, health_file=None):
    store = EventStore(tmp_path / "e.db", capacity=capacity)
    health = HealthState()
    pipeline = CounterPipeline(
        source=SyntheticSource(n_frames, fps=10.0, start_ts=T0),
        detector=ScriptedDetector(script),
        tracker=IouTracker(min_hits=2, max_age=10),
        counter=CrossingCounter(LINE, hysteresis=0.02, min_confirm_frames=2),
        store=store,
        health=health,
        identity=PipelineIdentity("cam-1", "synthetic"),
        health_file=health_file,
    )
    return pipeline, store, health


def test_pipeline_enter_then_exit(tmp_path):
    ys = walk(0.9, 0.1, 20) + walk(0.1, 0.9, 20)
    script = {i: [det(0.5, y)] for i, y in enumerate(ys)}
    pipeline, store, _ = _build_pipeline(tmp_path, script, len(ys))
    seen = []
    pipeline.run(on_event=seen.append)
    assert [e.event_type for e in seen] == [EventType.ENTER, EventType.EXIT]
    for e in seen:
        assert e.event_ts == T0 + timedelta(seconds=e.frame_index / 10.0)
    assert store.counts().pending == 2


def test_pipeline_buffer_full_is_loud(tmp_path, caplog):
    ys = walk(0.9, 0.1, 15) + walk(0.1, 0.9, 15) + walk(0.9, 0.1, 15)
    script = {i: [det(0.5, y)] for i, y in enumerate(ys)}
    pipeline, store, health = _build_pipeline(
        tmp_path, script, len(ys), capacity=1, health_file=str(tmp_path / "h.json")
    )
    with caplog.at_level(logging.ERROR):
        pipeline.run()
    snap = health.snapshot()
    assert snap.status == HealthStatus.BUFFER_FULL.value
    assert snap.events_lost_buffer_full == 2
    assert "EVENT LOST" in caplog.text


# ---------------------------------------------------------------------------
# CLI smoke tests
# ---------------------------------------------------------------------------
def _write_cli_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        f"""
device_id: dev-qa
camera_id: cam-qa
source:
  kind: synthetic
  synthetic_frames: 20
line:
  line_id: door
  ax: 0.1
  ay: 0.5
  bx: 0.9
  by: 0.5
  enter_side: left
detector:
  kind: scripted
store:
  path: {tmp_path}/events.sqlite3
  capacity: 100
health_file: {tmp_path}/health.json
""".strip()
    )
    return cfg


def _run_cli(args, cwd="/app/edge_agent"):
    return subprocess.run(
        [sys.executable, "-m", "edge_agent.cli", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_cli_run_no_send(tmp_path):
    cfg = _write_cli_config(tmp_path)
    r = _run_cli(["run", "--config", str(cfg), "--no-send"])
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    health_path = tmp_path / "health.json"
    assert health_path.exists()
    hd = json.loads(health_path.read_text())
    assert hd["status"] == "ok"
    assert hd["frames_processed"] == 20


def test_cli_status(tmp_path):
    cfg = _write_cli_config(tmp_path)
    # first run once to create db
    _run_cli(["run", "--config", str(cfg), "--no-send"])
    r = _run_cli(["status", "--config", str(cfg)])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert set(data.keys()) >= {"pending", "sent", "rejected", "capacity"}


def test_cli_schema():
    r = _run_cli(["schema"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "request" in data and "response" in data


# ---------------------------------------------------------------------------
# Contract SSOT guard
# ---------------------------------------------------------------------------
def test_contract_schema_equals_committed_file():
    on_disk = json.loads(Path("/app/contracts/event_v1.schema.json").read_text())
    generated = event_batch_json_schema()
    assert json.dumps(on_disk, sort_keys=True) == json.dumps(generated, sort_keys=True)


def test_naive_datetime_rejected():
    with pytest.raises(Exception):
        CountEventV1(
            event_id=uuid4(),
            event_type=EventType.ENTER,
            event_ts=datetime(2026, 1, 1, 0, 0, 0),  # naive
            camera_id="c",
            line_id="l",
            track_id=1,
            frame_index=0,
            source_kind="synthetic",
        )


def test_extra_tenant_id_rejected():
    with pytest.raises(Exception):
        CountEventV1(
            event_id=uuid4(),
            event_type=EventType.ENTER,
            event_ts=T0,
            camera_id="c",
            line_id="l",
            track_id=1,
            frame_index=0,
            source_kind="synthetic",
            tenant_id="tenant-1",  # forbidden
        )


# ---------------------------------------------------------------------------
# RtspVideoSource secret redaction
# ---------------------------------------------------------------------------
def test_rtsp_url_redacted_in_logs(caplog):
    url = "rtsp://user:secretpw@127.0.0.1:1/x"
    src = RtspVideoSource(url, max_reconnects=1, sleep=lambda d: None, reconnect_base_s=0.0)
    with caplog.at_level(logging.WARNING):
        frames = list(src.frames())
    assert frames == []
    assert "secretpw" not in caplog.text
    assert "***:***@127.0.0.1" in caplog.text
