"""Live API verification against the public preview URL.

Covers: health, stores list, ingest idempotency + summary/hourly deltas,
auth (missing/unknown key/wrong secret), validation (extra field, unknown camera,
naive ts, empty events), devices endpoint (last_seen_at, api_key_prefix, no full key leak),
unknown store 404. Cleans up synthetic rows at the end.
"""
import json
import os
import sqlite3
import uuid
from pathlib import Path

import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
if not BASE:
    # Fallback: read from frontend/.env
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE = line.split("=", 1)[1].strip().rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL missing"

SEED = json.loads(Path("/app/memory/seed_output.json").read_text())
API_KEY = SEED["device_api_key_SHOW_ONCE"]
STORE_ID = SEED["store_id"]
DB_PATH = "/app/backend/data/people_counter.sqlite3"

AUTH = {"Authorization": f"Bearer {API_KEY}"}
UNKNOWN_STORE = "00000000-0000-0000-0000-000000000000"
DATE = "2026-06-01"


def _event(event_id=None, event_ts="2026-06-01T02:15:00+00:00", camera_id="cam-door-front"):
    return {
        "schema_version": 1,
        "event_id": event_id or str(uuid.uuid4()),
        "event_type": "enter",
        "event_ts": event_ts,
        "camera_id": camera_id,
        "line_id": "door-1",
        "track_id": 1,
        "frame_index": 10,
        "source_kind": "synthetic",
    }


def _summary_enter():
    r = requests.get(f"{BASE}/api/v1/stores/{STORE_ID}/summary", params={"date": DATE}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module", autouse=True)
def cleanup_synthetic():
    # baseline cleanup up-front to keep test deterministic
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM count_events WHERE source_kind='synthetic'")
    conn.commit()
    conn.close()
    yield
    conn = sqlite3.connect(DB_PATH)
    deleted = conn.execute("DELETE FROM count_events WHERE source_kind='synthetic'").rowcount
    conn.commit()
    conn.close()
    print(f"[cleanup] deleted synthetic rows = {deleted}")


def test_health():
    r = requests.get(f"{BASE}/api/health", timeout=10)
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_stores_list_contains_pilot():
    r = requests.get(f"{BASE}/api/v1/stores", timeout=10)
    assert r.status_code == 200
    stores = r.json()
    match = [s for s in stores if s["store_id"] == STORE_ID]
    assert match, f"store_id {STORE_ID} not found; got {stores}"
    s = match[0]
    assert s["name"] == "Toko Pilot"
    assert s["timezone"] == "Asia/Jakarta"


def test_auth_missing():
    r = requests.post(f"{BASE}/api/v1/events/batch", json={"events": [_event()]}, timeout=10)
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate", "").lower().startswith("bearer")


def test_auth_unknown_key_id():
    r = requests.post(
        f"{BASE}/api/v1/events/batch",
        json={"events": [_event()]},
        headers={"Authorization": "Bearer dk_unknownxyz.somesecretvalue"},
        timeout=10,
    )
    assert r.status_code == 401


def test_auth_wrong_secret():
    key_id = API_KEY.split(".")[0]  # dk_<key_id>
    r = requests.post(
        f"{BASE}/api/v1/events/batch",
        json={"events": [_event()]},
        headers={"Authorization": f"Bearer {key_id}.wrongsecretvalue1234567890"},
        timeout=10,
    )
    assert r.status_code == 401


def test_validation_extra_field():
    ev = _event()
    ev["tenant_id"] = "3f398c57-9fad-438a-a066-1e00b1fe1cc4"
    r = requests.post(f"{BASE}/api/v1/events/batch", json={"events": [ev]}, headers=AUTH, timeout=10)
    assert r.status_code == 422, r.text


def test_validation_naive_ts():
    ev = _event(event_ts="2026-06-01T02:15:00")
    r = requests.post(f"{BASE}/api/v1/events/batch", json={"events": [ev]}, headers=AUTH, timeout=10)
    assert r.status_code == 422, r.text


def test_validation_empty_events():
    r = requests.post(f"{BASE}/api/v1/events/batch", json={"events": []}, headers=AUTH, timeout=10)
    assert r.status_code == 422, r.text


def test_unknown_camera_rejected():
    ev = _event(camera_id="cam-unknown")
    r = requests.post(f"{BASE}/api/v1/events/batch", json={"events": [ev]}, headers=AUTH, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] == []
    assert body["duplicates"] == []
    assert len(body["rejected"]) == 1
    assert body["rejected"][0]["event_id"] == ev["event_id"]
    assert body["rejected"][0]["reason"] == "unknown camera"
    # nothing counted
    s = _summary_enter()
    assert s["enter"] == 0


def test_ingest_idempotency_and_aggregates():
    baseline = _summary_enter()
    assert baseline["enter"] == 0, f"baseline should be 0, got {baseline}"

    ev = _event()
    body = {"events": [ev]}

    r1 = requests.post(f"{BASE}/api/v1/events/batch", json=body, headers=AUTH, timeout=15)
    assert r1.status_code == 200, r1.text
    j1 = r1.json()
    assert j1["accepted"] == [ev["event_id"]]
    assert j1["duplicates"] == []
    assert j1["rejected"] == []

    r2 = requests.post(f"{BASE}/api/v1/events/batch", json=body, headers=AUTH, timeout=15)
    assert r2.status_code == 200, r2.text
    j2 = r2.json()
    assert j2["accepted"] == []
    assert j2["duplicates"] == [ev["event_id"]]
    assert j2["rejected"] == []

    after = _summary_enter()
    assert after["enter"] == baseline["enter"] + 1, after
    assert after["timezone"] == "Asia/Jakarta"

    # hourly
    r = requests.get(f"{BASE}/api/v1/stores/{STORE_ID}/hourly", params={"date": DATE}, timeout=15)
    assert r.status_code == 200
    hourly = r.json()
    assert len(hourly["buckets"]) == 24
    assert hourly["buckets"][0]["hour_start"] == "2026-06-01T00:00:00+07:00"
    # 02:15 UTC == 09:15 WIB → bucket index 9
    b9 = hourly["buckets"][9]
    assert b9["enter"] == 1, b9
    assert b9["hour_start"].startswith("2026-06-01T09:00:00")


def test_devices_endpoint():
    r = requests.get(f"{BASE}/api/v1/stores/{STORE_ID}/devices", timeout=10)
    assert r.status_code == 200, r.text
    devices = r.json()
    match = [d for d in devices if d["name"] == "dev-pilot-01"]
    assert match, devices
    d = match[0]
    assert d["last_seen_at"] is not None
    # api_key_prefix == first 12 chars of the full key
    assert d["api_key_prefix"] == API_KEY[:12], (d["api_key_prefix"], API_KEY[:12])
    # full key must NOT be leaked anywhere in the response
    raw = r.text
    assert API_KEY not in raw
    secret = API_KEY.split(".", 1)[1]
    assert secret not in raw


def test_unknown_store_404():
    r = requests.get(f"{BASE}/api/v1/stores/{UNKNOWN_STORE}/summary", params={"date": DATE}, timeout=10)
    assert r.status_code == 404
