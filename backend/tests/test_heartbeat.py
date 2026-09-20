"""Finding 4: device liveness comes from heartbeats (device-authenticated), separate from visitor events."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from test_ingest import auth, event

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "edge_agent"))

from edge_agent.health import HealthState  # noqa: E402
from edge_agent.transport import HeartbeatSender  # noqa: E402

HB_PATH = "/api/v1/devices/heartbeat"


def hb(**over) -> dict:
    d = {"schema_version": 1, "sent_at": "2026-06-01T03:00:00+00:00", "source_status": "ok", "last_frame_age_s": 0.4,
         "pending_events": 0, "frames_processed": 120, "tracking_session_id": 1, "agent_version": "0.1.0"}
    d.update(over)
    return d


def _dev(client, fx, headers, store="store_a", name="dev-a") -> dict:
    devs = client.get(f"/api/v1/stores/{fx.ids[store]}/devices", headers=headers).json()
    return next(d for d in devs if d["name"] == name)


def test_heartbeat_requires_device_key(client, fx, auth_a):
    assert client.post(HB_PATH, json=hb()).status_code == 401
    assert client.post(HB_PATH, json=hb(), headers=auth("dk_bad.key")).status_code == 401
    assert client.post(HB_PATH, json=hb(), headers=auth(fx.keys["inactive"])).status_code == 403
    assert client.post(HB_PATH, json=hb(), headers=auth_a).status_code == 401  # dashboard JWT is not a device


def test_heartbeat_without_visitors_keeps_device_connected(client, fx, auth_a):
    before = datetime.now(timezone.utc)
    r = client.post(HB_PATH, json=hb(sent_at="2020-01-01T00:00:00+00:00"), headers=auth(fx.keys["a"]))
    assert r.status_code == 200
    received = datetime.fromisoformat(r.json()["received_at"])
    assert received >= before  # server clock, not the (old) edge sent_at
    d = _dev(client, fx, auth_a)
    assert datetime.fromisoformat(d["last_heartbeat_at"]) == received
    assert d["last_event_at"] is None  # heartbeat is not a visitor event
    assert (d["source_status"], d["last_frame_age_s"], d["pending_events"], d["agent_version"]) == ("ok", 0.4, 0, "0.1.0")


def test_heartbeat_does_not_change_visitor_counts(client, fx, auth_a):
    client.post("/api/v1/events/batch", json={"events": [event()]}, headers=auth(fx.keys["a"]))
    for _ in range(3):
        assert client.post(HB_PATH, json=hb(), headers=auth(fx.keys["a"])).status_code == 200
    s = client.get(f"/api/v1/stores/{fx.ids['store_a']}/summary?date=2026-06-01", headers=auth_a).json()
    assert (s["enter"], s["exit"]) == (1, 0)


def test_heartbeat_reports_camera_down_while_agent_alive(client, fx, auth_a):
    client.post(HB_PATH, json=hb(source_status="source_down", last_frame_age_s=95.0, pending_events=7), headers=auth(fx.keys["a"]))
    d = _dev(client, fx, auth_a)
    assert d["last_heartbeat_at"] is not None and d["source_status"] == "source_down"
    assert d["last_frame_age_s"] == 95.0 and d["pending_events"] == 7
    # recovery is reflected by the next heartbeat
    client.post(HB_PATH, json=hb(source_status="ok", last_frame_age_s=0.1), headers=auth(fx.keys["a"]))
    assert _dev(client, fx, auth_a)["source_status"] == "ok"


def test_heartbeat_only_updates_the_authenticated_device(client, fx, auth_a, auth_b):
    client.post(HB_PATH, json=hb(), headers=auth(fx.keys["b"]))
    assert _dev(client, fx, auth_a)["last_heartbeat_at"] is None
    assert _dev(client, fx, auth_a, name="dev-off")["last_heartbeat_at"] is None
    assert _dev(client, fx, auth_b, store="store_b", name="dev-b")["last_heartbeat_at"] is not None


def test_heartbeat_payload_validation(client, fx):
    h = auth(fx.keys["a"])
    assert client.post(HB_PATH, json=hb(device_id="spoof"), headers=h).status_code == 422
    assert client.post(HB_PATH, json=hb(pending_events=-1), headers=h).status_code == 422
    assert client.post(HB_PATH, json=hb(source_status="degraded"), headers=h).status_code == 422
    assert client.post(HB_PATH, json=hb(sent_at="2026-06-01T03:00:00"), headers=h).status_code == 422  # naive


def test_edge_heartbeat_sender_against_real_backend(client, fx, auth_a):
    health = HealthState()
    health.set_source(False)
    health.buffer_pending = 4
    sender = HeartbeatSender(health, str(client.base_url), fx.keys["a"], interval_s=60.0, client=client)
    assert sender.send_once() == 60.0 and sender.sent == 1
    d = _dev(client, fx, auth_a)
    assert d["source_status"] == "source_down" and d["pending_events"] == 4 and d["last_frame_age_s"] is None
    bad = HeartbeatSender(health, str(client.base_url), "dk_bad.key", interval_s=60.0, client=client)
    assert bad.send_once() >= 30.0 and bad.failed == 1  # backoff delay, nothing queued


def test_cross_store_device_list_is_tenant_scoped(client, fx, auth_a, auth_b):
    from conftest import login
    assert client.get("/api/v1/devices").status_code == 401
    assert client.get("/api/v1/devices", headers=auth(fx.keys["a"])).status_code == 401  # device key is not a user
    client.post(HB_PATH, json=hb(source_status="source_down"), headers=auth(fx.keys["a"]))
    devs = client.get("/api/v1/devices", headers=auth_a).json()
    assert sorted(d["name"] for d in devs) == ["dev-a", "dev-off"]  # tenant A only; dev-b (tenant B) absent
    assert all(d["store_name"] == "Toko A" and d["store_timezone"] == "Asia/Jakarta"
               and d["store_id"] == str(fx.ids["store_a"]) for d in devs)
    dev_a = next(d for d in devs if d["name"] == "dev-a")
    assert dev_a["source_status"] == "source_down" and dev_a["last_heartbeat_at"] is not None
    assert "secret_hash" not in str(devs) and "api_key_prefix" not in str(devs)
    assert [d["name"] for d in client.get("/api/v1/devices", headers=auth_b).json()] == ["dev-b"]
    assert client.get("/api/v1/devices", headers=login(client, "nobody@example.com")).json() == []
