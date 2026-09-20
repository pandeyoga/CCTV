"""ADR-028 alert rules + notification centre."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import update

from app.alerts import device_conditions, store_condition, DEFAULT_RULES
from app.db import Database
from app.models import Device, Store
from test_aggregates import post
from test_ingest import auth, event

HB = {"schema_version": 1, "sent_at": "2026-06-01T00:00:00Z", "source_status": "ok", "last_frame_age_s": 0.5,
      "pending_events": 0, "frames_processed": 1, "tracking_session_id": 0, "agent_version": "t"}
NOW = datetime(2026, 6, 1, 5, 0, tzinfo=timezone.utc)  # 12:00 WIB


def _dev(**kw) -> Device:
    d = Device(id=uuid4(), name="dev", is_active=True, last_heartbeat_at=NOW - timedelta(seconds=30), hb_source_status="ok", hb_pending_events=0)
    for k, v in kw.items():
        setattr(d, k, v)
    return d


def _age(client, db_url, device_id, minutes: int) -> None:
    """Push the device's last heartbeat into the past (synthetic clock; heartbeats are always server-stamped)."""
    async def run():
        db = Database(db_url)
        async with db.sessionmaker() as s:
            await s.execute(update(Device).where(Device.id == device_id).values(last_heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=minutes)))
            await s.commit()
        await db.dispose()
    asyncio.run(run())


# ----------------------------------------------------------------------------- pure decisions
def test_device_conditions():
    r = dict(DEFAULT_RULES)
    assert device_conditions(_dev(last_heartbeat_at=None), r, NOW, None) == []  # never heard -> unknown, no alert
    assert device_conditions(_dev(is_active=False, last_heartbeat_at=NOW - timedelta(hours=1)), r, NOW, None) == []
    assert device_conditions(_dev(), r, NOW, None) == []
    lost = device_conditions(_dev(last_heartbeat_at=NOW - timedelta(minutes=4)), r, NOW, None)
    assert [c.rule for c in lost] == ["heartbeat_lost"] and lost[0].since == NOW - timedelta(minutes=1)
    # dead agent: camera/buffer rules are suppressed
    assert [c.rule for c in device_conditions(_dev(last_heartbeat_at=NOW - timedelta(minutes=4), hb_source_status="source_down", hb_pending_events=5000), r, NOW, NOW - timedelta(hours=1))] == ["heartbeat_lost"]
    assert device_conditions(_dev(hb_source_status="source_down"), r, NOW, NOW - timedelta(minutes=1)) == []  # down < 2 min
    cam = device_conditions(_dev(hb_source_status="source_down"), r, NOW, NOW - timedelta(minutes=10))
    assert [c.rule for c in cam] == ["camera_down"] and cam[0].since == NOW - timedelta(minutes=8)
    assert [c.rule for c in device_conditions(_dev(hb_pending_events=1000), r, NOW, None)] == ["buffer_full"]
    assert device_conditions(_dev(hb_pending_events=999), r, NOW, None) == []


def test_store_condition():
    st = Store(id=uuid4(), name="Toko", timezone="Asia/Jakarta", open_time="09:00", close_time="21:00")
    r = dict(DEFAULT_RULES)
    assert store_condition(st, r, NOW, connected=True, has_camera=True, last_event=NOW - timedelta(minutes=30)) is None
    c = store_condition(st, r, NOW, connected=True, has_camera=True, last_event=NOW - timedelta(minutes=90))
    assert c and c.rule == "no_events_open_hours" and c.since == NOW - timedelta(minutes=30)
    assert store_condition(st, r, NOW, connected=False, has_camera=True, last_event=None) is None  # covered by heartbeat_lost
    assert store_condition(st, r, NOW, connected=True, has_camera=False, last_event=None) is None
    assert store_condition(st, {**r, "no_events_min": None}, NOW, True, True, None) is None  # rule off
    just_opened = datetime(2026, 6, 1, 2, 30, tzinfo=timezone.utc)  # 09:30 WIB, open only 30 min
    assert store_condition(st, r, just_opened, True, True, None) is None
    assert store_condition(st, r, NOW, True, True, None) is not None  # never any event, open > 60 min


# ----------------------------------------------------------------------------- endpoint flow
def test_heartbeat_lost_opens_then_resolves_and_ack(client, fx, auth_a, auth_b, auth_staff, db_url):
    dev = fx.ids["device_a"]
    assert client.put(f"/api/v1/stores/{fx.ids['store_a']}/alert-rules", json={"heartbeat_lost_min": 3, "camera_down_min": 2, "buffer_pending_threshold": 1000, "no_events_min": None}, headers=auth_a).status_code == 200
    assert client.get("/api/v1/alerts", headers=auth_a).json()["open_count"] == 0  # never heard -> no alert
    assert client.post("/api/v1/devices/heartbeat", json=HB, headers=auth(fx.keys["a"])).status_code == 200
    assert client.get("/api/v1/alerts", headers=auth_a).json()["open_count"] == 0
    _age(client, db_url, dev, 10)
    out = client.get("/api/v1/alerts", headers=auth_a).json()
    assert out["open_count"] == 1 and out["unacknowledged_count"] == 1
    a = out["alerts"][0]
    assert a["rule"] == "heartbeat_lost" and a["severity"] == "critical" and a["device_name"] == "dev-a" and a["store_name"] == "Toko A"
    assert a["resolved_at"] is None and a["acknowledged_at"] is None
    assert client.get("/api/v1/alerts", headers=auth_a).json()["open_count"] == 1  # idempotent: still one row
    # scoping
    assert client.get("/api/v1/alerts", headers=auth_b).json()["alerts"] == []
    assert client.post(f"/api/v1/alerts/{a['alert_id']}/ack", headers=auth_b).status_code == 404
    assert client.post(f"/api/v1/alerts/{a['alert_id']}/ack", headers=auth_staff).status_code == 403
    assert client.get("/api/v1/alerts").status_code == 401
    ack = client.post(f"/api/v1/alerts/{a['alert_id']}/ack", headers=auth_a).json()
    assert ack["acknowledged_at"] and ack["acknowledged_by_email"] == "owner-a@example.com"
    assert client.get("/api/v1/alerts", headers=auth_a).json()["unacknowledged_count"] == 0
    # heartbeat returns -> resolved, visible in history only
    assert client.post("/api/v1/devices/heartbeat", json=HB, headers=auth(fx.keys["a"])).status_code == 200
    out = client.get("/api/v1/alerts", headers=auth_a).json()
    assert out["open_count"] == 0 and out["alerts"] == []
    hist = client.get("/api/v1/alerts?status=resolved", headers=auth_a).json()["alerts"]
    assert len(hist) == 1 and hist[0]["resolved_at"] is not None
    assert len(client.get("/api/v1/alerts?status=all", headers=auth_a).json()["alerts"]) == 1
    assert client.get(f"/api/v1/alerts?store_id={fx.ids['store_b']}", headers=auth_a).status_code == 404


def test_buffer_full_and_closed_store_suppresses_new_alerts(client, fx, auth_a):
    sid = fx.ids["store_a"]
    assert client.put(f"/api/v1/stores/{sid}/alert-rules", json={"heartbeat_lost_min": 3, "camera_down_min": 2, "buffer_pending_threshold": 1000, "no_events_min": None}, headers=auth_a).status_code == 200
    assert client.post("/api/v1/devices/heartbeat", json={**HB, "pending_events": 1000}, headers=auth(fx.keys["a"])).status_code == 200
    rules = [a["rule"] for a in client.get("/api/v1/alerts", headers=auth_a).json()["alerts"]]
    assert rules == ["buffer_full"]
    # raise the threshold -> resolves
    assert client.put(f"/api/v1/stores/{sid}/alert-rules", json={"heartbeat_lost_min": 3, "camera_down_min": 2, "buffer_pending_threshold": 5000, "no_events_min": None}, headers=auth_a).status_code == 200
    assert client.get("/api/v1/alerts", headers=auth_a).json()["open_count"] == 0
    # closed store: condition true but no new incident
    now_local = datetime.now(timezone(timedelta(hours=7)))
    o, c = (now_local + timedelta(hours=2)).strftime("%H:%M"), (now_local + timedelta(hours=2, minutes=1)).strftime("%H:%M")
    assert client.patch(f"/api/v1/stores/{sid}", json={"open_time": o, "close_time": c}, headers=auth_a).status_code == 200
    assert client.put(f"/api/v1/stores/{sid}/alert-rules", json={"heartbeat_lost_min": 3, "camera_down_min": 2, "buffer_pending_threshold": 10, "no_events_min": None}, headers=auth_a).status_code == 200
    assert client.get("/api/v1/alerts", headers=auth_a).json()["open_count"] == 0
    assert client.patch(f"/api/v1/stores/{sid}", json={"open_time": None, "close_time": None}, headers=auth_a).status_code == 200
    assert client.get("/api/v1/alerts", headers=auth_a).json()["open_count"] == 1


def test_camera_down_uses_heartbeat_history(client, fx, auth_a, db_url):
    assert client.put(f"/api/v1/stores/{fx.ids['store_a']}/alert-rules", json={"heartbeat_lost_min": 3, "camera_down_min": 2, "buffer_pending_threshold": 1000, "no_events_min": None}, headers=auth_a).status_code == 200
    assert client.post("/api/v1/devices/heartbeat", json={**HB, "source_status": "source_down"}, headers=auth(fx.keys["a"])).status_code == 200
    assert client.get("/api/v1/alerts", headers=auth_a).json()["open_count"] == 0  # down for seconds only
    async def backdate():
        from app.models import DeviceHeartbeat
        db = Database(db_url)
        async with db.sessionmaker() as s:
            await s.execute(update(DeviceHeartbeat).where(DeviceHeartbeat.device_id == fx.ids["device_a"]).values(received_at=datetime.now(timezone.utc) - timedelta(minutes=5)))
            await s.commit()
        await db.dispose()
    asyncio.run(backdate())
    assert client.post("/api/v1/devices/heartbeat", json={**HB, "source_status": "source_down"}, headers=auth(fx.keys["a"])).status_code == 200
    out = client.get("/api/v1/alerts", headers=auth_a).json()
    assert [a["rule"] for a in out["alerts"]] == ["camera_down"]
    assert client.post("/api/v1/devices/heartbeat", json=HB, headers=auth(fx.keys["a"])).status_code == 200
    assert client.get("/api/v1/alerts", headers=auth_a).json()["open_count"] == 0


def test_no_events_open_hours(client, fx, auth_a):
    sid = fx.ids["store_a"]
    assert client.post("/api/v1/devices/heartbeat", json=HB, headers=auth(fx.keys["a"])).status_code == 200
    # 24 h store, connected device, camera present, no events ever -> fires with default 60 min
    assert [a["rule"] for a in client.get("/api/v1/alerts", headers=auth_a).json()["alerts"]] == ["no_events_open_hours"]
    post(client, fx.keys["a"], [event(ts=datetime.now(timezone.utc).isoformat(), event_type="enter")])
    assert client.get("/api/v1/alerts", headers=auth_a).json()["open_count"] == 0
    r = client.put(f"/api/v1/stores/{sid}/alert-rules", json={"heartbeat_lost_min": 3, "camera_down_min": 2, "buffer_pending_threshold": 1000, "no_events_min": 4}, headers=auth_a)
    assert r.status_code == 422  # min 5


def test_alert_rules_defaults_scoping_and_reset(client, fx, auth_a, auth_b, auth_staff):
    sid = fx.ids["store_a"]
    d = client.get(f"/api/v1/stores/{sid}/alert-rules", headers=auth_a).json()
    assert d["is_default"] is True and d["heartbeat_lost_min"] == 3 and d["no_events_min"] == 60
    assert client.get(f"/api/v1/stores/{sid}/alert-rules", headers=auth_staff).status_code == 200  # staff may read
    body = {"heartbeat_lost_min": 5, "camera_down_min": 3, "buffer_pending_threshold": 200, "no_events_min": 30}
    assert client.put(f"/api/v1/stores/{sid}/alert-rules", json=body, headers=auth_staff).status_code == 403
    assert client.put(f"/api/v1/stores/{sid}/alert-rules", json=body, headers=auth_b).status_code == 404
    saved = client.put(f"/api/v1/stores/{sid}/alert-rules", json=body, headers=auth_a).json()
    assert saved["is_default"] is False and saved["heartbeat_lost_min"] == 5
    assert client.get(f"/api/v1/stores/{sid}/alert-rules", headers=auth_a).json()["buffer_pending_threshold"] == 200
    assert client.put(f"/api/v1/stores/{sid}/alert-rules", json={**body, "extra": 1}, headers=auth_a).status_code == 422
    assert client.delete(f"/api/v1/stores/{sid}/alert-rules", headers=auth_a).json()["is_default"] is True
