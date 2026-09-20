"""ADR-026 opening hours + ADR-027 heartbeat history."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.routers.devices import build_segments
from test_aggregates import post
from test_ingest import auth, event

HB = {"schema_version": 1, "sent_at": "2026-06-01T00:00:00Z", "source_status": "ok", "last_frame_age_s": 0.5,
      "pending_events": 0, "frames_processed": 1, "tracking_session_id": 0, "agent_version": "t"}


# ----------------------------------------------------------------------------- opening hours
def test_store_hours_validation_and_roundtrip(client, fx, auth_a):
    sid = fx.ids["store_a"]
    p = lambda body: client.patch(f"/api/v1/stores/{sid}", json=body, headers=auth_a)  # noqa: E731
    assert p({"open_time": "09:00"}).status_code == 422  # must be set together
    assert p({"open_time": "9:00", "close_time": "21:00"}).status_code == 422
    assert p({"open_time": "09:00", "close_time": "09:00"}).status_code == 422
    assert p({"open_time": "24:00", "close_time": "09:00"}).status_code == 422
    r = p({"open_time": "09:00", "close_time": "21:00"})
    assert r.status_code == 200 and (r.json()["open_time"], r.json()["close_time"]) == ("09:00", "21:00")
    assert client.get("/api/v1/stores", headers=auth_a).json()[0]["open_time"] == "09:00"
    assert p({"name": "Toko A renamed"}).json()["open_time"] == "09:00"  # omitted -> unchanged
    assert p({"open_time": None, "close_time": None}).json()["open_time"] is None  # explicit null -> 24 h
    new = client.post("/api/v1/stores", json={"tenant_id": str(fx.ids["tenant_a"]), "name": "Malam", "timezone": "Asia/Jakarta",
                                                "open_time": "18:00", "close_time": "02:00"}, headers=auth_a)
    assert new.status_code == 201 and new.json()["close_time"] == "02:00"


def test_report_and_overview_ignore_closed_hours(client, fx, auth_a):
    sid = fx.ids["store_a"]
    assert client.patch(f"/api/v1/stores/{sid}", json={"open_time": "09:00", "close_time": "21:00"}, headers=auth_a).status_code == 200
    post(client, fx.keys["a"], [
        event(ts="2026-06-03T02:15:00+00:00", event_type="enter"),   # 09:15 WIB open
        event(ts="2026-06-03T13:59:00+00:00", event_type="enter"),   # 20:59 WIB open (close exclusive)
        event(ts="2026-06-03T14:00:00+00:00", event_type="enter"),   # 21:00 WIB closed
        event(ts="2026-06-03T01:59:00+00:00", event_type="exit"),    # 08:59 WIB closed
    ])
    r = client.get(f"/api/v1/stores/{sid}/report?from=2026-06-03&to=2026-06-03", headers=auth_a).json()
    assert (r["current"]["enter"], r["current"]["exit"], r["outside_hours_excluded"]) == (2, 0, 2)
    assert (r["open_time"], r["close_time"]) == ("09:00", "21:00")
    assert sum(h["enter"] for h in r["hourly_profile"] if h["hour"] < 9 or h["hour"] >= 21) == 0
    # 24 h store counts everything
    assert client.patch(f"/api/v1/stores/{sid}", json={"open_time": None, "close_time": None}, headers=auth_a).status_code == 200
    r = client.get(f"/api/v1/stores/{sid}/report?from=2026-06-03&to=2026-06-03", headers=auth_a).json()
    assert (r["current"]["enter"], r["current"]["exit"], r["outside_hours_excluded"]) == (3, 1, 0)


def test_overview_reports_closed_store_without_device_problems(client, fx, auth_a):
    sid = fx.ids["store_a"]
    now_local = datetime.now(timezone(timedelta(hours=7)))
    # a 1-minute window that is certainly closed right now
    closed_open = (now_local + timedelta(hours=2)).strftime("%H:%M")
    closed_close = (now_local + timedelta(hours=2, minutes=1)).strftime("%H:%M")
    assert client.patch(f"/api/v1/stores/{sid}", json={"open_time": closed_open, "close_time": closed_close}, headers=auth_a).status_code == 200
    row = client.get("/api/v1/overview", headers=auth_a).json()[0]
    assert row["is_open_now"] is False and row["devices_problem"] == 0 and row["devices_total"] == 1
    assert client.patch(f"/api/v1/stores/{sid}", json={"open_time": None, "close_time": None}, headers=auth_a).status_code == 200
    row = client.get("/api/v1/overview", headers=auth_a).json()[0]
    assert row["is_open_now"] is True and row["devices_problem"] == 1  # dev-a never sent a heartbeat


# ----------------------------------------------------------------------------- heartbeat history
def _t(minutes: int) -> datetime:
    return datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=minutes)


def test_build_segments_unknown_stale_and_merge():
    start, end = _t(0), _t(60)
    assert [(s.status, s.start, s.end) for s in build_segments([], start, end, 180)] == [("unknown", start, end)]
    samples = [(_t(10), "ok"), (_t(11), "ok"), (_t(12), "source_down"), (_t(13), "ok"), (_t(40), "ok")]
    segs = build_segments(samples, start, end, 180)
    got = [(s.status, int((s.start - start).total_seconds()), int((s.end - start).total_seconds())) for s in segs]
    assert got == [
        ("unknown", 0, 600),
        ("connected", 600, 720),        # 10:00-12:00 merged
        ("camera_down", 720, 780),
        ("connected", 780, 960),        # 13:00 + 180 s
        ("stale", 960, 2400),           # until 40:00
        ("connected", 2400, 2580),      # 40:00 + 180 s
        ("stale", 2580, 3600),
    ]
    # a sample before the window gives context for the first seconds
    segs = build_segments([(_t(-1), "ok"), (_t(1), "ok")], start, end, 180)
    assert segs[0].status == "connected" and segs[0].start == start


def test_heartbeat_history_endpoint_scoped_and_pruned(client, fx, auth_a, auth_b):
    dev = fx.ids["device_a"]
    h = client.get(f"/api/v1/devices/{dev}/heartbeats", headers=auth_a).json()
    assert h["samples"] == 0 and h["uptime_pct"] == 0 and [s["status"] for s in h["segments"]] == ["unknown"]
    assert client.post("/api/v1/devices/heartbeat", json=HB, headers=auth(fx.keys["a"])).status_code == 200
    assert client.post("/api/v1/devices/heartbeat", json={**HB, "source_status": "source_down"}, headers=auth(fx.keys["a"])).status_code == 200
    h = client.get(f"/api/v1/devices/{dev}/heartbeats?hours=1", headers=auth_a).json()
    assert h["samples"] == 2 and h["stale_after_s"] == 180
    statuses = [s["status"] for s in h["segments"]]
    assert statuses[0] == "unknown" and statuses[-1] == "camera_down" and "connected" in statuses
    assert client.get(f"/api/v1/devices/{dev}/heartbeats", headers=auth_b).status_code == 404
    assert client.get(f"/api/v1/devices/{dev}/heartbeats?hours=0", headers=auth_a).status_code == 422
    assert client.get(f"/api/v1/devices/{dev}/heartbeats?hours=169", headers=auth_a).status_code == 422
    assert client.get(f"/api/v1/devices/{dev}/heartbeats").status_code == 401
    assert client.get(f"/api/v1/devices/{dev}/heartbeats", headers=auth(fx.keys["a"])).status_code == 401  # device key never reads
