"""ADR-030/031 on the edge: zone geometry + sampling, config poller (reload without restart), snapshot uploader,
zone sample sender. Fake servers via httpx.MockTransport; no sleeps."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import numpy as np
import pytest

from edge_agent.contracts import DeviceConfigV1, ZoneSampleV1
from edge_agent.counting import CrossingCounter, DirectedLine, Zone, ZoneSampler, point_in_polygon
from edge_agent.detection.scripted import ScriptedDetector
from edge_agent.health import HealthState
from edge_agent.pipeline import CounterPipeline, PipelineIdentity
from edge_agent.storage import EventStore
from edge_agent.tracking import IouTracker
from edge_agent.transport import ConfigPoller, SnapshotUploader, ZoneSampleSender
from edge_agent.video.base import Frame

from helpers import det, track

SQUARE = ((0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8))
T0 = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)


# ----------------------------------------------------------------------------- geometry + sampler
def test_point_in_polygon_square_and_concave():
    assert point_in_polygon(0.5, 0.5, SQUARE) and not point_in_polygon(0.1, 0.5, SQUARE) and not point_in_polygon(0.5, 0.9, SQUARE)
    concave = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 0.5), (0.0, 1.0))  # notch at the bottom middle
    assert point_in_polygon(0.5, 0.2, concave) and not point_in_polygon(0.5, 0.8, concave)


def test_zone_requires_three_vertices():
    with pytest.raises(ValueError):
        Zone("z", ((0, 0), (1, 1)))


def test_zone_sampler_emits_per_interval_with_count_and_max():
    zs = ZoneSampler("cam", [Zone("kasir", SQUARE)], interval_s=10)
    # t=0..9s: 2 inside, then 1 inside; sample at t=10 must have count=1, count_max=2
    assert zs.update([track(1, 0.5, 0.5), track(2, 0.6, 0.6)], T0) == []
    assert zs.update([track(1, 0.5, 0.5)], T0 + timedelta(seconds=5)) == []
    out = zs.update([track(1, 0.5, 0.5), track(3, 0.05, 0.05)], T0 + timedelta(seconds=10))
    assert len(out) == 1 and isinstance(out[0], ZoneSampleV1)
    s = out[0]
    assert (s.camera_id, s.zone_id, s.count, s.count_max, s.interval_s) == ("cam", "kasir", 1, 2, 10.0) and s.sample_ts == T0 + timedelta(seconds=10)
    # next window: max restarts from the instantaneous count at the sample instant
    out2 = zs.update([], T0 + timedelta(seconds=20))
    assert out2[0].count == 0 and out2[0].count_max == 1
    # no zones -> nothing, and replacing zones restarts the window
    zs.set_zones([])
    assert zs.update([track(1, 0.5, 0.5)], T0 + timedelta(seconds=60)) == []
    zs.set_zones([Zone("a", SQUARE), Zone("b", ((0.0, 0.0), (0.1, 0.0), (0.1, 0.1), (0.0, 0.1)))])
    assert zs.update([track(1, 0.5, 0.5)], T0 + timedelta(seconds=70)) == []
    out3 = zs.update([track(1, 0.5, 0.5), track(2, 0.05, 0.05)], T0 + timedelta(seconds=80))
    assert {(s.zone_id, s.count) for s in out3} == {("a", 1), ("b", 1)}


# ----------------------------------------------------------------------------- pipeline: apply server config
def _pipeline(tmp_path, script, counter=None, sampler=None, sink=None):
    store = EventStore(str(tmp_path / "ev.sqlite3"), 1000)
    return CounterPipeline(source=None, detector=ScriptedDetector(script), tracker=IouTracker(0.1, 5, 1), counter=counter, store=store,
                           health=HealthState(), identity=PipelineIdentity("cam-door-front", "synthetic"), zone_sampler=sampler, on_zone_samples=sink)


def frame(i, img=None):
    return Frame(index=i, ts=T0 + timedelta(seconds=i), width=100, height=100, image=img)


def server_cfg(version="v1", line=None, zones=(), camera_id="cam-door-front"):
    return DeviceConfigV1(config_version=version, generated_at=T0, cameras=[{
        "camera_id": camera_id, "lines": [line] if line else [], "zones": list(zones)}])


def test_pipeline_without_line_counts_nothing_until_server_config_arrives(tmp_path):
    # person walks top -> bottom across y=0.5 over frames 0..9
    script = {i: [det(0.5, 0.2 + 0.07 * i)] for i in range(10)}
    p = _pipeline(tmp_path, script)
    for i in range(3):
        assert p.process_frame(frame(i)) == []
    p.apply_config(server_cfg(line={"line_id": "door-1", "ax": 0.1, "ay": 0.5, "bx": 0.9, "by": 0.5, "enter_side": "right"}))
    events = [e for i in range(3, 10) for e in p.process_frame(frame(i))]
    assert p.applied_config_version == "v1" and p.counter is not None and p.counter.line.line_id == "door-1"
    assert [e.event_type.value for e in events] == ["enter"] and events[0].line_id == "door-1"


def test_replace_line_keeps_totals_and_flips_direction(tmp_path):
    line = DirectedLine("door-1", 0.1, 0.5, 0.9, 0.5, "right")
    p = _pipeline(tmp_path, {}, counter=CrossingCounter(line, 0.02, 1, 30))
    p.counter.enter_count = 7
    p.apply_config(server_cfg("v2", line={"line_id": "door-1", "ax": 0.1, "ay": 0.5, "bx": 0.9, "by": 0.5, "enter_side": "left"}))
    p.process_frame(frame(0))
    assert p.counter.enter_count == 7 and p.counter.line.enter_side == "left" and p.applied_config_version == "v2"
    # identical geometry again -> same counter object (no reset)
    c = p.counter
    p.apply_config(server_cfg("v3", line={"line_id": "door-1", "ax": 0.1, "ay": 0.5, "bx": 0.9, "by": 0.5, "enter_side": "left"}))
    p.process_frame(frame(1))
    assert p.counter is c and p.applied_config_version == "v3"
    # config for another camera is ignored; config without a line keeps the current one
    p.apply_config(server_cfg("v4", camera_id="other"))
    p.process_frame(frame(2))
    assert p.counter is c and p.applied_config_version == "v3"
    p.apply_config(server_cfg("v5"))
    p.process_frame(frame(3))
    assert p.counter is c and p.applied_config_version == "v5"


def test_pipeline_zones_from_server_config_emit_samples_and_last_image(tmp_path):
    got: list[list[ZoneSampleV1]] = []
    script = {i: [det(0.5, 0.5)] for i in range(30)}
    p = _pipeline(tmp_path, script, counter=CrossingCounter(DirectedLine("l", 0, 0.9, 1, 0.9), 0.02, 1, 30),
                  sampler=ZoneSampler("cam-door-front", [], 10), sink=got.append)
    p.apply_config(server_cfg("z1", zones=[{"zone_id": "kasir", "name": "Kasir", "polygon": list(SQUARE)}]))
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    for i in range(25):
        p.process_frame(frame(i, img if i == 24 else None))
    assert p.last_image is img
    assert len(got) == 2 and got[0][0].zone_id == "kasir" and got[0][0].count == 1 and got[0][0].count_max == 1
    assert p.zone_sampler.zones[0].polygon == SQUARE


# ----------------------------------------------------------------------------- config poller
def test_config_poller_applies_only_on_version_change_and_backs_off():
    versions = iter(["v1", "v1", "v2"])
    state = {"fail": False, "calls": 0}
    applied = []

    def handler(req: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        assert req.headers["Authorization"] == "Bearer dk_k.s" and req.url.path == "/api/v1/devices/me/config"
        if state["fail"]:
            return httpx.Response(503)
        return httpx.Response(200, json=json.loads(server_cfg(next(versions)).model_dump_json()))

    poller = ConfigPoller("http://api", "dk_k.s", applied.append, interval_s=300, client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None)
    assert poller.poll_once() == 300 and [c.config_version for c in applied] == ["v1"]
    assert poller.poll_once() == 300 and len(applied) == 1  # same version: not re-applied
    assert poller.poll_once() == 300 and [c.config_version for c in applied] == ["v1", "v2"] and poller.applied_version == "v2"
    state["fail"] = True
    d1, d2 = poller.poll_once(), poller.poll_once()
    assert poller.failed == 2 and 0 < d1 <= 900 and 0 < d2 <= 900 and len(applied) == 2

    def bad(req):
        return httpx.Response(200, json={"schema_version": 1, "config_version": "x", "generated_at": "2026-06-01T00:00:00Z", "cameras": [{"camera_id": "c", "lines": [{"line_id": "l", "ax": 0.5, "ay": 0.5, "bx": 0.5, "by": 0.5, "enter_side": "left"}]}]})
    bad_poller = ConfigPoller("http://api", "dk_k.s", applied.append, interval_s=60, client=httpx.Client(transport=httpx.MockTransport(bad)))
    bad_poller.poll_once()
    assert bad_poller.failed == 1 and bad_poller.applied_version is None and len(applied) == 2  # invalid line rejected, nothing applied
    with pytest.raises(ValueError):
        ConfigPoller("http://api", "", applied.append)


# ----------------------------------------------------------------------------- snapshot uploader
def test_snapshot_uploader_posts_jpeg_and_skips_without_frame():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.url.params["camera_id"], req.headers["Content-Type"], req.content[:3]))
        return httpx.Response(200, json={"camera_id": "cam", "snapshot_at": "2026-06-01T00:00:00Z", "bytes": len(req.content)})

    images: list[np.ndarray | None] = [None]
    up = SnapshotUploader("cam", lambda: images[0], "http://api", "dk_k.s", interval_s=600, client=httpx.Client(transport=httpx.MockTransport(handler)),
                          encode=lambda img: b"\xff\xd8\xff" + bytes(img.shape[0]))
    assert up.send_once() == 600 and seen == [] and up.sent == 0
    images[0] = np.zeros((4, 4, 3), dtype=np.uint8)
    assert up.send_once() == 600 and seen == [("cam", "image/jpeg", b"\xff\xd8\xff")] and up.sent == 1


def test_encode_jpeg_downscales():
    cv2 = pytest.importorskip("cv2")
    from edge_agent.transport.snapshot import encode_jpeg
    data = encode_jpeg(np.zeros((1080, 1920, 3), dtype=np.uint8), max_width=960)
    assert data[:3] == b"\xff\xd8\xff"
    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert img.shape[:2] == (540, 960)


# ----------------------------------------------------------------------------- zone sample sender
def sample(zone="kasir"):
    return ZoneSampleV1(sample_id=uuid4(), camera_id="cam", zone_id=zone, sample_ts=T0, interval_s=10, count=1, count_max=2)


def test_zone_sample_sender_batches_dedups_and_drops_when_full():
    received: list[dict] = []
    mode = {"status": 200}

    def handler(req: httpx.Request) -> httpx.Response:
        if mode["status"] != 200:
            return httpx.Response(mode["status"])
        body = json.loads(req.content)
        received.append(body)
        ids = [s["sample_id"] for s in body["samples"]]
        return httpx.Response(200, json={"accepted": ids[:-1], "duplicates": [], "rejected": [{"sample_id": ids[-1], "reason": "unknown zone"}]})

    zs = ZoneSampleSender("http://api", "dk_k.s", batch_size=2, max_queue=3, interval_s=5, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert zs.send_once() == 5  # empty queue
    zs.enqueue([sample(), sample(), sample(), sample()])  # 4 into a queue of 3 -> oldest dropped
    assert zs.pending == 3 and zs.dropped == 1
    mode["status"] = 503
    delay = zs.send_once()
    assert zs.pending == 3 and delay > 0
    mode["status"] = 200
    assert zs.send_once() == 0.0 and zs.pending == 1 and len(received[-1]["samples"]) == 2 and zs.sent == 1 and zs.rejected == 1
    assert zs.send_once() == 5 and zs.pending == 0
    assert all("dk_k.s" not in json.dumps(b) for b in received)
