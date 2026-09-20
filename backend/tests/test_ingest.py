from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


def event(camera_id="cam-a", ts="2026-06-01T03:00:00+00:00", event_type="enter", event_id=None, **extra) -> dict:
    d = {"schema_version": 1, "event_id": str(event_id or uuid4()), "event_type": event_type, "event_ts": ts,
         "camera_id": camera_id, "line_id": "door-1", "track_id": 1, "frame_index": 10, "source_kind": "synthetic"}
    d.update(extra)
    return d


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_missing_key_401(client):
    r = client.post("/api/v1/events/batch", json={"events": [event()]})
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"


def test_wrong_secret_401(client, fx, auth_a):
    key_id = fx.keys["a"].split(".")[0]
    r = client.post("/api/v1/events/batch", json={"events": [event()]}, headers=auth(f"{key_id}.wrong"))
    assert r.status_code == 401


def test_malformed_token_401(client):
    assert client.post("/api/v1/events/batch", json={"events": [event()]}, headers=auth("nonsense")).status_code == 401


def test_inactive_device_403(client, fx, auth_a):
    r = client.post("/api/v1/events/batch", json={"events": [event()]}, headers=auth(fx.keys["inactive"]))
    assert r.status_code == 403


def test_accept_then_duplicate(client, fx, auth_a):
    ev = event()
    r1 = client.post("/api/v1/events/batch", json={"events": [ev]}, headers=auth(fx.keys["a"]))
    assert r1.status_code == 200 and r1.json() == {"accepted": [ev["event_id"]], "duplicates": [], "rejected": []}
    r2 = client.post("/api/v1/events/batch", json={"events": [ev]}, headers=auth(fx.keys["a"]))
    assert r2.json() == {"accepted": [], "duplicates": [ev["event_id"]], "rejected": []}
    # duplicate inside the same batch
    ev2 = event()
    r3 = client.post("/api/v1/events/batch", json={"events": [ev2, ev2]}, headers=auth(fx.keys["a"]))
    assert r3.json()["accepted"] == [ev2["event_id"]] and r3.json()["duplicates"] == [ev2["event_id"]]


def test_unknown_camera_rejected_not_stored(client, fx, auth_a):
    ev = event(camera_id="cam-does-not-exist")
    r = client.post("/api/v1/events/batch", json={"events": [ev]}, headers=auth(fx.keys["a"]))
    assert r.json() == {"accepted": [], "duplicates": [], "rejected": [{"event_id": ev["event_id"], "reason": "unknown camera"}]}


def test_tenant_isolation_camera_of_other_tenant_rejected(client, fx, auth_b):
    auth_a = auth_b  # store_b is readable only by tenant B's user
    ev = event(camera_id="cam-b")  # belongs to Tenant B; device A must not be able to post to it
    r = client.post("/api/v1/events/batch", json={"events": [ev]}, headers=auth(fx.keys["a"]))
    assert r.json()["rejected"][0]["reason"] == "unknown camera"
    s = client.get(f"/api/v1/stores/{fx.ids['store_b']}/summary?date=2026-06-01", headers=auth_a).json()
    assert (s["enter"], s["exit"]) == (0, 0)


def test_identity_fields_in_payload_are_rejected_422(client, fx, auth_a):
    ev = event(tenant_id="spoof")
    assert client.post("/api/v1/events/batch", json={"events": [ev]}, headers=auth(fx.keys["a"])).status_code == 422


def test_naive_timestamp_rejected_422(client, fx, auth_a):
    ev = event(ts="2026-06-01T03:00:00")
    assert client.post("/api/v1/events/batch", json={"events": [ev]}, headers=auth(fx.keys["a"])).status_code == 422


def test_empty_batch_422(client, fx, auth_a):
    assert client.post("/api/v1/events/batch", json={"events": []}, headers=auth(fx.keys["a"])).status_code == 422


def test_ingest_updates_last_event_at_not_heartbeat(client, fx, auth_a):
    client.post("/api/v1/events/batch", json={"events": [event()]}, headers=auth(fx.keys["a"]))
    devs = client.get(f"/api/v1/stores/{fx.ids['store_a']}/devices", headers=auth_a).json()
    dev_a = next(d for d in devs if d["name"] == "dev-a")
    assert dev_a["last_event_at"] is not None
    assert dev_a["last_heartbeat_at"] is None  # visitor events are not liveness (Finding 4)
    assert "api_key_prefix" not in dev_a and "last_seen_at" not in dev_a
    assert fx.keys["a"] not in str(devs) and fx.keys["a"][:12] not in str(devs)


def test_tracking_session_id_optional_and_stored(client, fx, auth_a):
    ev_old = event()  # pre-Finding-2 agent: no tracking_session_id
    ev_new = event(tracking_session_id=3)
    r = client.post("/api/v1/events/batch", json={"events": [ev_old, ev_new]}, headers=auth(fx.keys["a"]))
    assert r.status_code == 200 and len(r.json()["accepted"]) == 2
    assert client.post("/api/v1/events/batch", json={"events": [event(tracking_session_id=-1)]},
                       headers=auth(fx.keys["a"])).status_code == 422


def test_health_public(client):
    assert client.get("/api/health").json() == {"status": "ok"}
