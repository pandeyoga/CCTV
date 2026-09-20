"""Live QA — ADR-026 opening hours + ADR-027 heartbeat history against preview URL.

Run: pytest backend/tests/qa_live_hours_history.py -v -o addopts=""
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://cctv-system-1.preview.emergentagent.com").rstrip("/")
OWNER = ("owner@tokopilot.id", "Owner-Pilot-2026!")


@pytest.fixture(scope="session")
def owner_token():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": OWNER[0], "password": OWNER[1]}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def owner_headers(owner_token):
    return {"Authorization": f"Bearer {owner_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def toko_pilot(owner_headers):
    r = requests.get(f"{BASE}/api/v1/stores", headers=owner_headers, timeout=15)
    assert r.status_code == 200
    stores = r.json()
    s = next(x for x in stores if x["name"] == "Toko Pilot")
    return s


@pytest.fixture(scope="session")
def dev_pilot_01(owner_headers, toko_pilot):
    r = requests.get(f"{BASE}/api/v1/stores/{toko_pilot['store_id']}/devices", headers=owner_headers, timeout=15)
    assert r.status_code == 200
    devs = r.json()
    d = next(x for x in devs if x["name"] == "dev-pilot-01")
    return d


# --------------------------------------------------------------- opening hours
def _patch(headers, sid, body):
    return requests.patch(f"{BASE}/api/v1/stores/{sid}", json=body, headers=headers, timeout=15)


def test_hours_validation_and_roundtrip(owner_headers, toko_pilot):
    sid = toko_pilot["store_id"]
    # ensure baseline null hours; restore at end
    try:
        assert _patch(owner_headers, sid, {"open_time": "09:00"}).status_code == 422
        assert _patch(owner_headers, sid, {"open_time": "9:00", "close_time": "21:00"}).status_code == 422
        assert _patch(owner_headers, sid, {"open_time": "09:00", "close_time": "09:00"}).status_code == 422
        r = _patch(owner_headers, sid, {"open_time": "09:00", "close_time": "21:00"})
        assert r.status_code == 200
        j = r.json()
        assert j["open_time"] == "09:00" and j["close_time"] == "21:00"
        # persisted in list
        lst = requests.get(f"{BASE}/api/v1/stores", headers=owner_headers, timeout=15).json()
        s = next(x for x in lst if x["store_id"] == sid)
        assert s["open_time"] == "09:00" and s["close_time"] == "21:00"
        # name-only patch keeps hours
        r = _patch(owner_headers, sid, {"name": toko_pilot["name"]})
        assert r.status_code == 200 and r.json()["open_time"] == "09:00"
        # explicit null -> 200 with nulls
        r = _patch(owner_headers, sid, {"open_time": None, "close_time": None})
        assert r.status_code == 200
        assert r.json()["open_time"] is None and r.json()["close_time"] is None
    finally:
        _patch(owner_headers, sid, {"open_time": None, "close_time": None})


def test_report_and_overview_hours_semantics(owner_headers, toko_pilot):
    sid = toko_pilot["store_id"]
    try:
        assert _patch(owner_headers, sid, {"open_time": "09:00", "close_time": "21:00"}).status_code == 200
        today = datetime.now(timezone(timedelta(hours=7))).date()
        frm = (today - timedelta(days=6)).isoformat()
        to = today.isoformat()
        r = requests.get(f"{BASE}/api/v1/stores/{sid}/report?from={frm}&to={to}", headers=owner_headers, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["open_time"] == "09:00" and j["close_time"] == "21:00"
        assert isinstance(j["outside_hours_excluded"], int) and j["outside_hours_excluded"] >= 0
        for h in j["hourly_profile"]:
            if h["hour"] < 9 or h["hour"] >= 21:
                assert h["enter"] == 0 and h["exit"] == 0, f"closed hour {h['hour']} has traffic"
        # overview row has is_open_now + hours echoed
        ov = requests.get(f"{BASE}/api/v1/overview", headers=owner_headers, timeout=15).json()
        row = next(x for x in ov if x["store_id"] == sid)
        assert isinstance(row["is_open_now"], bool)
        assert row["open_time"] == "09:00" and row["close_time"] == "21:00"
    finally:
        _patch(owner_headers, sid, {"open_time": None, "close_time": None})


def test_overview_closed_now_no_device_problems(owner_headers, toko_pilot):
    sid = toko_pilot["store_id"]
    try:
        now_local = datetime.now(timezone(timedelta(hours=7)))
        o = (now_local + timedelta(hours=2)).strftime("%H:%M")
        c = (now_local + timedelta(hours=2, minutes=1)).strftime("%H:%M")
        assert _patch(owner_headers, sid, {"open_time": o, "close_time": c}).status_code == 200
        ov = requests.get(f"{BASE}/api/v1/overview", headers=owner_headers, timeout=15).json()
        row = next(x for x in ov if x["store_id"] == sid)
        assert row["is_open_now"] is False, row
        assert row["devices_problem"] == 0, row
    finally:
        r = _patch(owner_headers, sid, {"open_time": None, "close_time": None})
        assert r.status_code == 200 and r.json()["open_time"] is None


# --------------------------------------------------------------- heartbeat history
def test_heartbeat_history_shape(owner_headers, dev_pilot_01):
    did = dev_pilot_01["device_id"]
    r = requests.get(f"{BASE}/api/v1/devices/{did}/heartbeats", headers=owner_headers, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["stale_after_s"] == 180
    assert isinstance(j["samples"], int)
    assert 0.0 <= j["uptime_pct"] <= 100.0
    segs = j["segments"]
    assert len(segs) >= 1
    allowed = {"connected", "camera_down", "stale", "unknown"}
    for s in segs:
        assert s["status"] in allowed, s
    # contiguous: each end == next start
    for a, b in zip(segs, segs[1:]):
        assert a["end"] == b["start"], (a, b)
    # bounds match from_ts..to_ts
    assert segs[0]["start"] == j["from_ts"]
    assert segs[-1]["end"] == j["to_ts"]


def test_heartbeat_history_validation(owner_headers, dev_pilot_01):
    did = dev_pilot_01["device_id"]
    assert requests.get(f"{BASE}/api/v1/devices/{did}/heartbeats?hours=0", headers=owner_headers, timeout=10).status_code == 422
    assert requests.get(f"{BASE}/api/v1/devices/{did}/heartbeats?hours=169", headers=owner_headers, timeout=10).status_code == 422
    assert requests.get(f"{BASE}/api/v1/devices/{did}/heartbeats", timeout=10).status_code == 401
    fake = str(uuid.uuid4())
    assert requests.get(f"{BASE}/api/v1/devices/{fake}/heartbeats", headers=owner_headers, timeout=10).status_code == 404


HB = {"schema_version": 1, "sent_at": "2026-06-01T00:00:00Z", "source_status": "ok", "last_frame_age_s": 0.5,
      "pending_events": 0, "frames_processed": 1, "tracking_session_id": 0, "agent_version": "qa-live"}


def test_heartbeat_post_increments_and_deactivates(owner_headers, toko_pilot):
    sid = toko_pilot["store_id"]
    uniq = uuid.uuid4().hex[:8]
    r = requests.post(f"{BASE}/api/v1/stores/{sid}/devices", json={"name": f"TEST_hb_{uniq}"}, headers=owner_headers, timeout=15)
    assert r.status_code in (200, 201), r.text
    dev = r.json()
    dev_obj = dev.get("device", dev)
    did = dev_obj.get("device_id") or dev_obj.get("id")
    key = dev.get("api_key_show_once") or dev.get("device_key")
    assert key, f"no device_key in response: {dev}"
    try:
        khdr = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        r1 = requests.post(f"{BASE}/api/v1/devices/heartbeat", json={**HB, "sent_at": now_iso}, headers=khdr, timeout=10)
        assert r1.status_code == 200, r1.text
        r2 = requests.post(f"{BASE}/api/v1/devices/heartbeat",
                           json={**HB, "sent_at": now_iso, "source_status": "source_down"},
                           headers=khdr, timeout=10)
        assert r2.status_code == 200, r2.text
        h = requests.get(f"{BASE}/api/v1/devices/{did}/heartbeats?hours=1", headers=owner_headers, timeout=15).json()
        assert h["samples"] == 2, h
        assert h["segments"][-1]["status"] == "camera_down", h["segments"][-1]
    finally:
        requests.patch(f"{BASE}/api/v1/devices/{did}", json={"is_active": False}, headers=owner_headers, timeout=10)
