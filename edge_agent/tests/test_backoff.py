"""Finding 5: backoff must be overflow-safe, bounded, reset on success, and interruptible on shutdown."""
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import pytest

from edge_agent.contracts import CountEventV1, EventType
from edge_agent.health import HealthState
from edge_agent.storage import EventStore
from edge_agent.transport import Backoff, EventSender, HeartbeatSender, SendOutcome, interruptible_wait
from edge_agent.video.rtsp_source import RtspVideoSource


def test_10000_failures_do_not_overflow_and_stay_within_bounds():
    bo = Backoff(1.0, 60.0, rng=lambda: 0.999)
    delays = [bo.next_delay() for _ in range(10_000)]
    assert all(0.5 <= d <= 60.0 for d in delays)
    assert delays[-1] == 60.0 and bo.failures == 10_000


def test_legacy_expression_would_overflow():
    with pytest.raises(OverflowError):
        min(60.0, 1.0 * (2 ** 5000) * 1.0)  # float conversion of a huge int


def test_max_backoff_bounds_delay_after_jitter():
    bo = Backoff(1.0, 8.0, rng=lambda: 0.999)   # jitter x1.999 would exceed the cap
    for _ in range(10):
        assert bo.next_delay() <= 8.0


def test_reset_returns_to_initial_delay():
    bo = Backoff(1.0, 60.0, rng=lambda: 0.5)    # jitter factor exactly 1.0
    assert [bo.next_delay() for _ in range(4)] == [1.0, 2.0, 4.0, 8.0]
    bo.reset()
    assert bo.next_delay() == 1.0


def _event():
    return CountEventV1(event_id=uuid4(), event_type=EventType.ENTER, event_ts=datetime(2026, 6, 1, tzinfo=timezone.utc),
                        camera_id="c", line_id="l", track_id=1, frame_index=1, source_kind="synthetic")


def test_sender_event_id_stable_across_many_failures_then_success_resets_backoff(tmp_path):
    store = EventStore(tmp_path / "e.db", capacity=10)
    ev = _event()
    store.append(ev)
    seen_ids, state = [], {"fail": True}

    def handler(req: httpx.Request):
        body = req.read().decode()
        seen_ids.append(body)
        if state["fail"]:
            return httpx.Response(503)
        return httpx.Response(200, json={"accepted": [str(ev.event_id)], "duplicates": [], "rejected": []})

    sleeps = []
    sender = EventSender(store, "http://backend", "dk_x.y", HealthState(), client=httpx.Client(transport=httpx.MockTransport(handler)),
                         base_backoff_s=1.0, max_backoff_s=30.0, sleep=sleeps.append, rng=lambda: 0.5)
    results = [sender.send_once() for _ in range(200)]
    assert all(r.outcome is SendOutcome.RETRY for r in results)
    assert max(r.next_delay_s for r in results) <= 30.0 and sender.failures == 200
    assert len({s for s in seen_ids}) == 1  # identical body (same event_id) on every retry
    state["fail"] = False
    ok = sender.send_once()
    assert ok.outcome is SendOutcome.SENT and store.status_of(ev.event_id) == "sent" and sender.failures == 0
    store.append(_event())
    state["fail"] = True
    assert sender.send_once().next_delay_s == 1.0  # back to the initial delay


def test_run_forever_stops_promptly_during_a_long_backoff(tmp_path):
    store = EventStore(tmp_path / "e.db", capacity=10)
    store.append(_event())
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(503)))
    calls = {"n": 0}
    slept = []

    def fake_sleep(s):
        slept.append(s)
        calls["n"] += 1

    def stop():
        return calls["n"] >= 3  # request shutdown after three sleep slices

    sender = EventSender(store, "http://backend", "dk_x.y", HealthState(), client=client, base_backoff_s=1000.0,
                         max_backoff_s=1000.0, sleep=fake_sleep, rng=lambda: 0.5)
    sender.run_forever(stop)
    assert len(slept) == 3 and all(s <= 0.5 for s in slept)   # did not sleep the full 1000 s
    assert store.counts().pending == 1                          # never marked sent without an ack


def test_interruptible_wait_slices():
    slept = []
    interruptible_wait(1.2, lambda: False, slept.append)
    assert slept == [0.5, 0.5, pytest.approx(0.2)]


def test_rtsp_reconnect_backoff_is_bounded_and_overflow_safe(monkeypatch):
    import edge_agent.video.rtsp_source as mod

    class FakeCap:
        def __init__(self, *a): pass
        def isOpened(self): return False
        def release(self): pass

    monkeypatch.setattr(mod.cv2, "VideoCapture", FakeCap)
    sleeps = []
    src = RtspVideoSource("rtsp://u:p@cam/stream", reconnect_base_s=1.0, reconnect_max_s=30.0, max_reconnects=5000, sleep=sleeps.append)
    assert list(src.frames()) == []
    assert len(sleeps) >= 5000 and max(sleeps) <= 30.0 and min(sleeps) >= 0.5


def test_heartbeat_sender_backoff_and_no_backlog():
    health = HealthState()
    calls = []
    client = httpx.Client(transport=httpx.MockTransport(lambda req: (calls.append(req.read()), httpx.Response(503))[1]))
    hb = HeartbeatSender(health, "http://backend", "dk_x.y", interval_s=60.0, client=client, max_backoff_s=300.0)
    delays = [hb.send_once() for _ in range(50)]
    assert all(30.0 <= d <= 300.0 for d in delays) and hb.failed == 50 and len(calls) == 50  # one request per attempt, no queue
