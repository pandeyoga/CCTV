"""Live QA tests for ADR-028 Alerts (list, ack, rules, buffer_full flow).
Runs against REACT_APP_BACKEND_URL preview.  Idempotent-friendly:
* Restores per-store alert rules to defaults via DELETE at the end.
* Deactivates any TEST_alert_* device it creates (no delete API).
* Never posts heartbeats for dev-pilot-01, never posts count events.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
OWNER = ("owner@tokopilot.id", "Owner-Pilot-2026!")
STAFF = ("staff@tokopilot.id", "Staff-Pilot-2026!")
STORE_ID = "01db25d6-ca01-400f-8b52-59c3120a58f7"
DEV_PILOT_01 = "9336a6b8-94c4-492f-ba23-d5f8facfa3b4"

VALID_RULES = {"heartbeat_lost", "camera_down", "buffer_full", "no_events_open_hours"}
VALID_SEV = {"warning", "critical"}


def _login(email: str, password: str) -> str:
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def owner_h():
    return {"Authorization": f"Bearer {_login(*OWNER)}"}


@pytest.fixture(scope="module")
def staff_h():
    return {"Authorization": f"Bearer {_login(*STAFF)}"}


# ---------------- LIST ----------------
class TestList:
    def test_no_auth_401(self):
        r = requests.get(f"{BASE}/api/v1/alerts", timeout=15)
        assert r.status_code == 401, r.text

    def test_default_open(self, owner_h):
        r = requests.get(f"{BASE}/api/v1/alerts", headers=owner_h, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert set(data) >= {"evaluated_at", "open_count", "unacknowledged_count", "alerts"}
        assert isinstance(data["open_count"], int)
        assert isinstance(data["unacknowledged_count"], int)
        assert isinstance(data["alerts"], list)
        for a in data["alerts"]:
            assert set(a) >= {"alert_id", "store_name", "device_name", "rule", "severity", "message",
                              "opened_at", "last_seen_at", "resolved_at", "acknowledged_at", "acknowledged_by_email"}
            assert a["rule"] in VALID_RULES
            assert a["severity"] in VALID_SEV
            assert a["resolved_at"] is None  # status=open default
        # must have >=1 heartbeat_lost open for dev-pilot-01
        hb = [a for a in data["alerts"] if a["rule"] == "heartbeat_lost"]
        assert hb, "expected at least one open heartbeat_lost alert (dev-pilot-01)"

    def test_status_resolved_and_all(self, owner_h):
        for s in ("resolved", "all"):
            r = requests.get(f"{BASE}/api/v1/alerts", headers=owner_h, params={"status": s}, timeout=20)
            assert r.status_code == 200, (s, r.text)
            assert isinstance(r.json()["alerts"], list)

    def test_status_bogus_422(self, owner_h):
        r = requests.get(f"{BASE}/api/v1/alerts", headers=owner_h, params={"status": "bogus"}, timeout=15)
        assert r.status_code == 422, r.text

    def test_random_store_404(self, owner_h):
        r = requests.get(f"{BASE}/api/v1/alerts", headers=owner_h, params={"store_id": str(uuid.uuid4())}, timeout=15)
        assert r.status_code == 404, r.text


# ---------------- ACK ----------------
class TestAck:
    def _first_unacked(self, headers):
        d = requests.get(f"{BASE}/api/v1/alerts", headers=headers, timeout=20).json()
        return next((a for a in d["alerts"] if a["acknowledged_at"] is None), None), d

    def test_random_uuid_404(self, owner_h):
        r = requests.post(f"{BASE}/api/v1/alerts/{uuid.uuid4()}/ack", headers=owner_h, timeout=15)
        assert r.status_code == 404, r.text

    def test_staff_ack_forbidden(self, owner_h, staff_h):
        unacked, _ = self._first_unacked(owner_h)
        # ensure an unacked exists via buffer_full flow if needed
        created_dev = None
        try:
            if unacked is None:
                created_dev = _create_buffer_full_alert(owner_h)
                unacked, _ = self._first_unacked(owner_h)
            assert unacked is not None, "cannot get an unacked alert"
            r = requests.post(f"{BASE}/api/v1/alerts/{unacked['alert_id']}/ack", headers=staff_h, timeout=15)
            assert r.status_code == 403, r.text
        finally:
            if created_dev:
                _deactivate(owner_h, created_dev)

    def test_owner_ack_idempotent(self, owner_h):
        unacked, _ = self._first_unacked(owner_h)
        created_dev = None
        try:
            if unacked is None:
                created_dev = _create_buffer_full_alert(owner_h)
                unacked, _ = self._first_unacked(owner_h)
            assert unacked is not None
            aid = unacked["alert_id"]
            r1 = requests.post(f"{BASE}/api/v1/alerts/{aid}/ack", headers=owner_h, timeout=15)
            assert r1.status_code == 200, r1.text
            a1 = r1.json()
            assert a1["acknowledged_at"] is not None
            assert a1["acknowledged_by_email"] == OWNER[0]
            r2 = requests.post(f"{BASE}/api/v1/alerts/{aid}/ack", headers=owner_h, timeout=15)
            assert r2.status_code == 200
            a2 = r2.json()
            assert a2["acknowledged_at"] == a1["acknowledged_at"], "ack must be idempotent"
        finally:
            if created_dev:
                _deactivate(owner_h, created_dev)


# ---------------- RULES ----------------
class TestRules:
    def test_get_default(self, owner_h):
        r = requests.get(f"{BASE}/api/v1/stores/{STORE_ID}/alert-rules", headers=owner_h, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        # Note: may be non-default from earlier iteration; we just record and continue
        assert d["heartbeat_lost_min"] >= 1
        assert d["camera_down_min"] >= 1
        assert d["buffer_pending_threshold"] >= 1
        if not d["is_default"]:
            print("NOTE: alert rules were not at defaults on entry:", d)

    def test_staff_get_ok(self, staff_h):
        r = requests.get(f"{BASE}/api/v1/stores/{STORE_ID}/alert-rules", headers=staff_h, timeout=15)
        assert r.status_code == 200, r.text

    def test_staff_put_403(self, staff_h):
        r = requests.put(f"{BASE}/api/v1/stores/{STORE_ID}/alert-rules", headers=staff_h,
                         json={"heartbeat_lost_min": 5, "camera_down_min": 3, "buffer_pending_threshold": 200, "no_events_min": 30}, timeout=15)
        assert r.status_code == 403, r.text

    def test_owner_put_ok(self, owner_h):
        r = requests.put(f"{BASE}/api/v1/stores/{STORE_ID}/alert-rules", headers=owner_h,
                         json={"heartbeat_lost_min": 5, "camera_down_min": 3, "buffer_pending_threshold": 200, "no_events_min": 30}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["is_default"] is False
        assert d["heartbeat_lost_min"] == 5
        assert d["no_events_min"] == 30

    def test_put_no_events_too_small_422(self, owner_h):
        r = requests.put(f"{BASE}/api/v1/stores/{STORE_ID}/alert-rules", headers=owner_h,
                         json={"heartbeat_lost_min": 5, "camera_down_min": 3, "buffer_pending_threshold": 200, "no_events_min": 4}, timeout=15)
        assert r.status_code == 422, r.text

    def test_put_extra_field_422(self, owner_h):
        r = requests.put(f"{BASE}/api/v1/stores/{STORE_ID}/alert-rules", headers=owner_h,
                         json={"heartbeat_lost_min": 5, "camera_down_min": 3, "buffer_pending_threshold": 200, "no_events_min": 30, "extra": 1}, timeout=15)
        assert r.status_code == 422, r.text

    def test_put_missing_field_422(self, owner_h):
        r = requests.put(f"{BASE}/api/v1/stores/{STORE_ID}/alert-rules", headers=owner_h,
                         json={"heartbeat_lost_min": 5, "camera_down_min": 3, "buffer_pending_threshold": 200}, timeout=15)
        assert r.status_code == 422, r.text

    def test_zzz_delete_restores_defaults(self, owner_h):
        r = requests.delete(f"{BASE}/api/v1/stores/{STORE_ID}/alert-rules", headers=owner_h, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["is_default"] is True
        assert d["heartbeat_lost_min"] == 3
        assert d["camera_down_min"] == 2
        assert d["buffer_pending_threshold"] == 1000
        assert d["no_events_min"] == 60


# ---------------- BUFFER FULL FLOW ----------------
def _create_test_device(owner_h) -> tuple[str, str]:
    name = f"TEST_alert_{uuid.uuid4().hex[:8]}"
    r = requests.post(f"{BASE}/api/v1/stores/{STORE_ID}/devices", headers=owner_h, json={"name": name}, timeout=15)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    return body["device"]["device_id"], body["api_key_show_once"]


def _heartbeat(api_key: str, pending: int) -> requests.Response:
    return requests.post(f"{BASE}/api/v1/devices/heartbeat",
                         headers={"Authorization": f"Bearer {api_key}"},
                         json={"schema_version": 1, "sent_at": "2026-06-01T00:00:00Z", "source_status": "ok",
                               "last_frame_age_s": 0.5, "pending_events": pending, "frames_processed": 1,
                               "tracking_session_id": 0, "agent_version": "qa"}, timeout=15)


def _deactivate(owner_h, device_id: str) -> None:
    requests.patch(f"{BASE}/api/v1/devices/{device_id}", headers=owner_h, json={"is_active": False}, timeout=15)


def _create_buffer_full_alert(owner_h) -> str:
    """Helper: create test device + heartbeat with pending 1000, returns device_id (caller must deactivate)."""
    did, key = _create_test_device(owner_h)
    r = _heartbeat(key, 1000)
    assert r.status_code == 200, r.text
    # Trigger evaluator
    requests.get(f"{BASE}/api/v1/alerts", headers=owner_h, timeout=20)
    return did


class TestBufferFullFlow:
    def test_full_flow(self, owner_h):
        did, key = _create_test_device(owner_h)
        try:
            r = _heartbeat(key, 1000)
            assert r.status_code == 200, r.text
            time.sleep(0.5)
            d = requests.get(f"{BASE}/api/v1/alerts", headers=owner_h, timeout=20).json()
            match = [a for a in d["alerts"] if a["rule"] == "buffer_full" and a["device_id"] == did]
            assert match, f"expected buffer_full alert for device {did}, alerts={[(a['rule'], a['device_id']) for a in d['alerts']]}"
            m = match[0]
            assert m["severity"] == "warning"
            assert m["device_name"].startswith("TEST_alert_")
            # Resolve
            r2 = _heartbeat(key, 0)
            assert r2.status_code == 200, r2.text
            time.sleep(0.5)
            d2 = requests.get(f"{BASE}/api/v1/alerts", headers=owner_h, timeout=20).json()
            assert not [a for a in d2["alerts"] if a["rule"] == "buffer_full" and a["device_id"] == did], "buffer_full should be resolved"
            d3 = requests.get(f"{BASE}/api/v1/alerts", headers=owner_h, params={"status": "resolved"}, timeout=20).json()
            resolved = [a for a in d3["alerts"] if a["rule"] == "buffer_full" and a["device_id"] == did]
            assert resolved and resolved[0]["resolved_at"] is not None
        finally:
            _deactivate(owner_h, did)
            # Verify deactivation removes any lingering alerts for this device from OPEN list
            time.sleep(0.5)
            d4 = requests.get(f"{BASE}/api/v1/alerts", headers=owner_h, timeout=20).json()
            assert not [a for a in d4["alerts"] if a["device_id"] == did], "no open alerts should linger for deactivated TEST device"
