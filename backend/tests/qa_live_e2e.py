"""Live E2E API checks against a deployed backend (testing-agent artefact, iteration_6).
Deliberately outside the `test_*.py` glob: it posts synthetic events to a REAL server and must only be run
on purpose (`pytest tests/qa_live_e2e.py`) with REACT_APP_BACKEND_URL set, followed by cleanup of count_events."""
import os
import json
import uuid
from datetime import datetime, timezone

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")  # no default: never hit a server by accident

with open("/app/memory/seed_output.json") as f:
    SEED = json.load(f)

DEVICE_KEY = SEED["device_api_key_SHOW_ONCE"]
STORE_ID = SEED["store_id"]
DEVICE_ID = SEED["device_id"]

OWNER_EMAIL = "owner@example.com"
OWNER_PASSWORD = "PilotOwner#2026"


@pytest.fixture(scope="session")
def jwt_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def user_headers(jwt_token):
    return {"Authorization": f"Bearer {jwt_token}"}


@pytest.fixture(scope="session")
def device_headers():
    return {"Authorization": f"Bearer {DEVICE_KEY}"}


# ----- Public + Unauth -----
def test_health_public():
    r = requests.get(f"{BASE_URL}/api/health")
    assert r.status_code == 200


@pytest.mark.parametrize("path", [
    "/api/v1/stores",
    f"/api/v1/stores/{{sid}}/summary",
    f"/api/v1/stores/{{sid}}/hourly",
    f"/api/v1/stores/{{sid}}/devices",
])
def test_unauth_returns_401_with_bearer_challenge(path):
    p = path.format(sid=STORE_ID)
    r = requests.get(f"{BASE_URL}{p}")
    assert r.status_code == 401, f"{p} => {r.status_code}"
    www = r.headers.get("WWW-Authenticate", "")
    assert "Bearer" in www, f"{p} WWW-Authenticate={www!r}"


# ----- Login -----
def test_login_success(jwt_token):
    # fixture already asserted 200
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    d = r.json()
    assert d["token_type"].lower() == "bearer"
    assert isinstance(d.get("expires_in"), int)
    u = d["user"]
    assert u["email"] == OWNER_EMAIL
    assert "user_id" in u and "tenant_ids" in u and isinstance(u["tenant_ids"], list)


def test_login_wrong_password_401():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": OWNER_EMAIL, "password": "definitelyWrong!"})
    assert r.status_code == 401, r.text


def test_login_unknown_email_401():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "nobody-xyz@example.com", "password": "whatever"})
    assert r.status_code == 401, r.text


def test_login_extra_field_422():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD, "extra": "x"})
    assert r.status_code == 422, r.text


# ----- Auth cross-scope + tampered -----
def test_device_key_on_user_endpoint_401(device_headers):
    r = requests.get(f"{BASE_URL}/api/v1/stores", headers=device_headers)
    assert r.status_code == 401


def test_user_jwt_on_device_batch_401(user_headers):
    payload = {"schema_version": 1, "device_id": DEVICE_ID, "events": []}
    r = requests.post(f"{BASE_URL}/api/v1/events/batch", headers=user_headers, json=payload)
    assert r.status_code == 401


def test_tampered_jwt_401(jwt_token):
    tampered = jwt_token[:-2] + ("aa" if jwt_token[-2:] != "aa" else "bb")
    r = requests.get(f"{BASE_URL}/api/v1/stores", headers={"Authorization": f"Bearer {tampered}"})
    assert r.status_code == 401


# ----- Stores/scoping -----
def test_list_stores_single_toko_pilot(user_headers):
    r = requests.get(f"{BASE_URL}/api/v1/stores", headers=user_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list) and len(data) == 1
    s = data[0]
    assert s["name"] == "Toko Pilot"
    assert s["timezone"] == "Asia/Jakarta"


def test_summary_hourly_devices_200(user_headers):
    for suffix in ("summary", "hourly", "devices"):
        r = requests.get(f"{BASE_URL}/api/v1/stores/{STORE_ID}/{suffix}", headers=user_headers)
        assert r.status_code == 200, f"{suffix} => {r.status_code} {r.text}"


def test_random_store_404(user_headers):
    r = requests.get(f"{BASE_URL}/api/v1/stores/{uuid.uuid4()}/summary", headers=user_headers)
    assert r.status_code == 404


# ----- Heartbeat -----
def test_heartbeat_ok(device_headers, user_headers):
    # capture pre state
    pre = requests.get(f"{BASE_URL}/api/v1/stores/{STORE_ID}/devices", headers=user_headers).json()
    pre_last_event = pre[0].get("last_event_at")
    pre_summary = requests.get(f"{BASE_URL}/api/v1/stores/{STORE_ID}/summary", headers=user_headers).json()

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    body = {
        "schema_version": 1,
        "sent_at": now,
        "source_status": "ok",
        "last_frame_age_s": 0.5,
        "pending_events": 0,
        "frames_processed": 10,
        "tracking_session_id": 0,
        "agent_version": "0.1.0",
    }
    r = requests.post(f"{BASE_URL}/api/v1/devices/heartbeat", headers=device_headers, json=body)
    assert r.status_code == 200, r.text
    assert "received_at" in r.json()

    # Verify device state
    post = requests.get(f"{BASE_URL}/api/v1/stores/{STORE_ID}/devices", headers=user_headers).json()
    d = post[0]
    assert d["source_status"] == "ok"
    assert d.get("last_heartbeat_at") is not None
    assert d.get("last_event_at") == pre_last_event  # unchanged

    post_summary = requests.get(f"{BASE_URL}/api/v1/stores/{STORE_ID}/summary", headers=user_headers).json()
    # heartbeat should not change enter/exit
    for k in ("enter_count", "exit_count"):
        if k in pre_summary and k in post_summary:
            assert pre_summary[k] == post_summary[k]


def test_heartbeat_without_key_401():
    r = requests.post(f"{BASE_URL}/api/v1/devices/heartbeat", json={"schema_version": 1, "sent_at": "2026-01-01T00:00:00Z",
                                                                     "source_status": "ok", "last_frame_age_s": 0.1,
                                                                     "pending_events": 0, "frames_processed": 1,
                                                                     "tracking_session_id": 0, "agent_version": "0.1.0"})
    assert r.status_code == 401


def test_heartbeat_extra_field_422(device_headers):
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    body = {"schema_version": 1, "sent_at": now, "source_status": "ok", "last_frame_age_s": 0.5,
            "pending_events": 0, "frames_processed": 1, "tracking_session_id": 0, "agent_version": "0.1.0",
            "device_id": DEVICE_ID}
    r = requests.post(f"{BASE_URL}/api/v1/devices/heartbeat", headers=device_headers, json=body)
    assert r.status_code == 422, r.text


# ----- Events batch (synthetic, then CLEANUP) -----
def test_events_batch_with_and_without_tracking_session(device_headers):
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    e1_id = str(uuid.uuid4())
    e2_id = str(uuid.uuid4())
    events = [
        {"schema_version": 1, "event_id": e1_id, "event_type": "enter", "event_ts": now_iso,
         "camera_id": "cam-door-front", "line_id": "door-1", "track_id": 1, "frame_index": 10,
         "source_kind": "synthetic", "tracking_session_id": 2},
        {"schema_version": 1, "event_id": e2_id, "event_type": "exit", "event_ts": now_iso,
         "camera_id": "cam-door-front", "line_id": "door-1", "track_id": 2, "frame_index": 11,
         "source_kind": "synthetic"},  # no tracking_session_id (backward compat)
    ]
    payload = {"events": events}
    r = requests.post(f"{BASE_URL}/api/v1/events/batch", headers=device_headers, json=payload)
    assert r.status_code in (200, 201, 202), r.text
    data = r.json()
    assert len(data.get("accepted", [])) >= 1

    # duplicate re-post
    r2 = requests.post(f"{BASE_URL}/api/v1/events/batch", headers=device_headers, json=payload)
    assert r2.status_code in (200, 201, 202), r2.text
    d2 = r2.json()
    assert len(d2.get("duplicates", [])) >= 1


def test_zzz_cleanup_synthetic_events():
    """Cleanup synthetic events from SQLite so pilot DB has no fake data."""
    import sqlite3
    conn = sqlite3.connect("/app/backend/data/people_counter.sqlite3")
    conn.execute("DELETE FROM count_events;")
    conn.execute("UPDATE devices SET last_seen_at=NULL;")
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM count_events").fetchone()[0]
    conn.close()
    assert n == 0
