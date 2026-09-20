"""Live API verification of Phase 1 self-service management (ADR-024) against preview URL.

Covers: platform admin login + tenants; owner store CRUD (validation + duplicate); device create + heartbeat +
rotate-key invalidation + is_active gating; cameras (cross-store 422, invalid external_id 422, patch clear_device,
delete 204); members (create staff, staff RBAC 403s, role patch, self-role 409, reset-password); admin user list +
deactivate (staff token now 401); change-password success/wrong-current/short.

Run with `pytest backend/tests/qa_live_manage.py -v -o addopts=""` — must be SERIAL (module-level `_STATE`
threads store_id/device_id/camera_id/staff_user_id between tests, so DO NOT pass -n auto). Cleans up devices
(deactivate) + staff membership but not stores themselves (no DELETE store API). Never touches seeded
owner/admin passwords.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE:
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE = line.split("=", 1)[1].strip()
BASE = BASE.rstrip("/")

ADMIN = ("admin@peoplecounter.app", "Admin-Pilot-2026!")
OWNER = ("owner@tokopilot.id", "Owner-Pilot-2026!")

UNIQ = uuid.uuid4().hex[:6]  # test run identifier so names don't collide across reruns


def _login(email: str, password: str) -> dict:
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text}"
    return r.json()


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------- session-scoped state ----------------------
@pytest.fixture(scope="session")
def admin_login():
    return _login(*ADMIN)


@pytest.fixture(scope="session")
def owner_login():
    return _login(*OWNER)


@pytest.fixture(scope="session")
def admin_token(admin_login):
    return admin_login["access_token"]


@pytest.fixture(scope="session")
def owner_token(owner_login):
    return owner_login["access_token"]


@pytest.fixture(scope="session")
def tenant_id(owner_token) -> str:
    r = requests.get(f"{BASE}/api/v1/tenants", headers=_h(owner_token), timeout=15)
    assert r.status_code == 200, r.text
    tenants = r.json()
    assert any(t["name"] == "Pilot Tenant" for t in tenants), tenants
    for t in tenants:
        if t["name"] == "Pilot Tenant":
            assert t["role"] == "owner", t
            return t["tenant_id"]


# store this test run creates so downstream tests can use it
_STATE: dict = {}


# ==================== ADMIN LOGIN / TENANTS ====================
class TestAdminLogin:
    def test_admin_login_flags(self, admin_login):
        u = admin_login["user"]
        assert u["email"] == ADMIN[0]
        assert u.get("is_platform_admin") is True

    def test_admin_tenants_include_pilot_with_role(self, admin_token):
        r = requests.get(f"{BASE}/api/v1/tenants", headers=_h(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        ts = r.json()
        pilot = [t for t in ts if t["name"] == "Pilot Tenant"]
        assert pilot, ts
        assert pilot[0]["role"] == "platform_admin"


# ==================== OWNER STORES ====================
class TestOwnerStores:
    def test_create_store_success(self, owner_token, tenant_id):
        name = f"TEST_Store_{UNIQ}"
        r = requests.post(f"{BASE}/api/v1/stores", headers=_h(owner_token),
                          json={"tenant_id": tenant_id, "name": name, "timezone": "Asia/Jakarta"}, timeout=15)
        assert r.status_code == 201, r.text
        st = r.json()
        assert st["name"] == name
        assert st["timezone"] == "Asia/Jakarta"
        assert st["tenant_id"] == tenant_id
        _STATE["store_id"] = st["store_id"]
        _STATE["store_name"] = name

    def test_create_store_invalid_tz_422(self, owner_token, tenant_id):
        r = requests.post(f"{BASE}/api/v1/stores", headers=_h(owner_token),
                          json={"tenant_id": tenant_id, "name": f"TEST_TzBad_{UNIQ}", "timezone": "Mars/Olympus"}, timeout=15)
        assert r.status_code == 422, r.text

    def test_create_store_duplicate_name_409(self, owner_token, tenant_id):
        r = requests.post(f"{BASE}/api/v1/stores", headers=_h(owner_token),
                          json={"tenant_id": tenant_id, "name": _STATE["store_name"], "timezone": "Asia/Jakarta"}, timeout=15)
        assert r.status_code == 409, r.text

    def test_patch_store_rename(self, owner_token):
        new_name = f"TEST_Store_{UNIQ}_r"
        r = requests.patch(f"{BASE}/api/v1/stores/{_STATE['store_id']}", headers=_h(owner_token),
                           json={"name": new_name}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["name"] == new_name
        _STATE["store_name"] = new_name


# ==================== DEVICES ====================
class TestDevices:
    def test_create_device_returns_key(self, owner_token):
        r = requests.post(f"{BASE}/api/v1/stores/{_STATE['store_id']}/devices", headers=_h(owner_token),
                          json={"name": f"TEST_dev_{UNIQ}"}, timeout=15)
        assert r.status_code == 201, r.text
        j = r.json()
        assert "api_key_show_once" in j
        assert j["api_key_show_once"].startswith("dk_"), j
        _STATE["device_id"] = j["device"]["device_id"]
        _STATE["device_key"] = j["api_key_show_once"]

    def test_heartbeat_with_new_key_ok(self):
        body = {
            "schema_version": 1,
            "sent_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source_status": "ok",
            "last_frame_age_s": 1.0,
            "pending_events": 0,
            "frames_processed": 1,
            "tracking_session_id": 0,
            "agent_version": "qa",
        }
        r = requests.post(f"{BASE}/api/v1/devices/heartbeat", headers=_h(_STATE["device_key"]), json=body, timeout=15)
        assert r.status_code == 200, r.text

    def test_rotate_key_invalidates_old(self, owner_token):
        old_key = _STATE["device_key"]
        r = requests.post(f"{BASE}/api/v1/devices/{_STATE['device_id']}/rotate-key", headers=_h(owner_token), timeout=15)
        assert r.status_code == 200, r.text
        new_key = r.json()["api_key_show_once"]
        assert new_key.startswith("dk_")
        assert new_key != old_key
        _STATE["device_key"] = new_key
        # old key must now 401
        body = {"schema_version": 1, "sent_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "source_status": "ok", "last_frame_age_s": 1.0, "pending_events": 0,
                "frames_processed": 1, "tracking_session_id": 0, "agent_version": "qa"}
        r2 = requests.post(f"{BASE}/api/v1/devices/heartbeat", headers=_h(old_key), json=body, timeout=15)
        assert r2.status_code == 401, r2.text

    def test_deactivate_device_blocks_heartbeat_403(self, owner_token):
        r = requests.patch(f"{BASE}/api/v1/devices/{_STATE['device_id']}", headers=_h(owner_token),
                           json={"is_active": False}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["is_active"] is False
        body = {"schema_version": 1, "sent_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "source_status": "ok", "last_frame_age_s": 1.0, "pending_events": 0,
                "frames_processed": 1, "tracking_session_id": 0, "agent_version": "qa"}
        r2 = requests.post(f"{BASE}/api/v1/devices/heartbeat", headers=_h(_STATE["device_key"]), json=body, timeout=15)
        assert r2.status_code == 403, r2.text
        # reactivate for downstream tests (camera reassignment)
        requests.patch(f"{BASE}/api/v1/devices/{_STATE['device_id']}", headers=_h(owner_token),
                       json={"is_active": True}, timeout=15)


# ==================== CAMERAS ====================
class TestCameras:
    def test_list_cameras_initially_seed(self, owner_token):
        r = requests.get(f"{BASE}/api/v1/stores/{_STATE['store_id']}/cameras", headers=_h(owner_token), timeout=15)
        assert r.status_code == 200
        assert r.json() == []  # brand new store

    def test_create_camera_invalid_external_id_422(self, owner_token):
        r = requests.post(f"{BASE}/api/v1/stores/{_STATE['store_id']}/cameras", headers=_h(owner_token),
                          json={"external_id": "cam qa", "name": "Bad"}, timeout=15)
        assert r.status_code == 422, r.text

    def test_create_camera_cross_store_device_422(self, owner_token):
        # seeded device dev-pilot-01 belongs to Toko Pilot (a different store)
        # Find that device id
        tenants = requests.get(f"{BASE}/api/v1/tenants", headers=_h(owner_token)).json()
        tid = [t for t in tenants if t["name"] == "Pilot Tenant"][0]["tenant_id"]
        stores = requests.get(f"{BASE}/api/v1/stores", headers=_h(owner_token)).json()
        toko_pilot = [s for s in stores if s.get("name") == "Toko Pilot"][0]
        devs = requests.get(f"{BASE}/api/v1/stores/{toko_pilot['store_id']}/devices", headers=_h(owner_token)).json()
        assert devs, devs
        other_device_id = devs[0]["device_id"]
        _ = tid

        r = requests.post(f"{BASE}/api/v1/stores/{_STATE['store_id']}/cameras", headers=_h(owner_token),
                          json={"external_id": f"camqa-{UNIQ}", "name": "Cross", "device_id": other_device_id}, timeout=15)
        assert r.status_code == 422, r.text

    def test_create_camera_success(self, owner_token):
        r = requests.post(f"{BASE}/api/v1/stores/{_STATE['store_id']}/cameras", headers=_h(owner_token),
                          json={"external_id": f"camqa-{UNIQ}", "name": "QA Cam", "device_id": _STATE["device_id"]}, timeout=15)
        assert r.status_code == 201, r.text
        c = r.json()
        assert c["device_id"] == _STATE["device_id"]
        _STATE["camera_id"] = c["camera_id"]

    def test_patch_camera_clear_device(self, owner_token):
        r = requests.patch(f"{BASE}/api/v1/cameras/{_STATE['camera_id']}", headers=_h(owner_token),
                           json={"clear_device": True}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["device_id"] is None

    def test_delete_camera_204(self, owner_token):
        r = requests.delete(f"{BASE}/api/v1/cameras/{_STATE['camera_id']}", headers=_h(owner_token), timeout=15)
        assert r.status_code == 204, r.text


# ==================== MEMBERS + RBAC ====================
STAFF_EMAIL = f"TEST_qa-staff-{UNIQ}@example.com"
STAFF_PW = "Staff-QA-2026!"


class TestMembers:
    def test_owner_creates_staff(self, owner_token, tenant_id):
        r = requests.post(f"{BASE}/api/v1/tenants/{tenant_id}/members", headers=_h(owner_token),
                          json={"email": STAFF_EMAIL, "role": "staff", "password": STAFF_PW}, timeout=15)
        assert r.status_code == 201, r.text
        m = r.json()
        assert m["role"] == "staff"
        _STATE["staff_user_id"] = m["user_id"]

    def test_staff_login_and_rbac(self, tenant_id):
        r = requests.post(f"{BASE}/api/auth/login", json={"email": STAFF_EMAIL, "password": STAFF_PW}, timeout=15)
        assert r.status_code == 200, r.text
        st_token = r.json()["access_token"]
        _STATE["staff_token"] = st_token
        # staff can list stores
        r1 = requests.get(f"{BASE}/api/v1/stores", headers=_h(st_token), timeout=15)
        assert r1.status_code == 200
        # 403 on create store
        r2 = requests.post(f"{BASE}/api/v1/stores", headers=_h(st_token),
                           json={"tenant_id": tenant_id, "name": f"TEST_StaffTry_{UNIQ}", "timezone": "Asia/Jakarta"}, timeout=15)
        assert r2.status_code == 403, r2.text
        # 403 on GET members
        r3 = requests.get(f"{BASE}/api/v1/tenants/{tenant_id}/members", headers=_h(st_token), timeout=15)
        assert r3.status_code == 403, r3.text
        # 403 on POST tenants
        r4 = requests.post(f"{BASE}/api/v1/tenants", headers=_h(st_token),
                           json={"name": f"TEST_StaffT_{UNIQ}"}, timeout=15)
        assert r4.status_code == 403, r4.text

    def test_owner_patch_member_role_roundtrip(self, owner_token, tenant_id):
        uid = _STATE["staff_user_id"]
        r = requests.patch(f"{BASE}/api/v1/tenants/{tenant_id}/members/{uid}", headers=_h(owner_token),
                           json={"role": "owner"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "owner"
        r2 = requests.patch(f"{BASE}/api/v1/tenants/{tenant_id}/members/{uid}", headers=_h(owner_token),
                            json={"role": "staff"}, timeout=15)
        assert r2.status_code == 200, r2.text
        assert r2.json()["role"] == "staff"

    def test_owner_cannot_change_own_role(self, owner_token, owner_login, tenant_id):
        my_id = owner_login["user"]["user_id"]
        r = requests.patch(f"{BASE}/api/v1/tenants/{tenant_id}/members/{my_id}", headers=_h(owner_token),
                           json={"role": "staff"}, timeout=15)
        assert r.status_code == 409, r.text

    def test_owner_reset_staff_password(self, owner_token):
        uid = _STATE["staff_user_id"]
        new_pw = "Staff-QA-Reset-2026!"
        r = requests.post(f"{BASE}/api/v1/users/{uid}/reset-password", headers=_h(owner_token),
                          json={"password": new_pw}, timeout=15)
        assert r.status_code == 204, r.text
        # staff can login with new password
        r2 = requests.post(f"{BASE}/api/auth/login", json={"email": STAFF_EMAIL, "password": new_pw}, timeout=15)
        assert r2.status_code == 200, r2.text
        _STATE["staff_token"] = r2.json()["access_token"]
        _STATE["staff_pw"] = new_pw

    def test_owner_post_tenants_403(self, owner_token):
        r = requests.post(f"{BASE}/api/v1/tenants", headers=_h(owner_token),
                          json={"name": f"TEST_OwnerT_{UNIQ}"}, timeout=15)
        assert r.status_code == 403, r.text

    def test_owner_get_users_403(self, owner_token):
        r = requests.get(f"{BASE}/api/v1/users", headers=_h(owner_token), timeout=15)
        assert r.status_code == 403, r.text


# ==================== ADMIN USERS ====================
class TestAdminUsers:
    def test_admin_lists_all_users(self, admin_token):
        r = requests.get(f"{BASE}/api/v1/users", headers=_h(admin_token), timeout=15)
        assert r.status_code == 200, r.text
        users = r.json()
        emails = {u["email"] for u in users}
        assert ADMIN[0] in emails
        assert OWNER[0] in emails
        assert STAFF_EMAIL.lower() in emails
        # memberships shape
        for u in users:
            if u["email"] == STAFF_EMAIL.lower():
                assert any(m["role"] == "staff" for m in u["memberships"]), u

    def test_admin_deactivate_staff_then_reactivate(self, admin_token):
        uid = _STATE["staff_user_id"]
        r = requests.patch(f"{BASE}/api/v1/users/{uid}", headers=_h(admin_token), json={"is_active": False}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["is_active"] is False
        # staff token should now 401 on protected endpoint
        r2 = requests.get(f"{BASE}/api/v1/stores", headers=_h(_STATE["staff_token"]), timeout=15)
        assert r2.status_code == 401, r2.text
        # reactivate
        r3 = requests.patch(f"{BASE}/api/v1/users/{uid}", headers=_h(admin_token), json={"is_active": True}, timeout=15)
        assert r3.status_code == 200, r3.text
        assert r3.json()["is_active"] is True


# ==================== CHANGE PASSWORD ====================
class TestChangePassword:
    def test_wrong_current_403(self):
        # Login with current staff pw to get fresh token
        r = requests.post(f"{BASE}/api/auth/login", json={"email": STAFF_EMAIL, "password": _STATE["staff_pw"]}, timeout=15)
        assert r.status_code == 200, r.text
        tok = r.json()["access_token"]
        r2 = requests.post(f"{BASE}/api/auth/change-password", headers=_h(tok),
                           json={"current_password": "WrongOldPassw123!", "new_password": "NewValidPw-2026!"}, timeout=15)
        assert r2.status_code == 403, r2.text
        _STATE["staff_token_fresh"] = tok

    def test_short_new_password_422(self):
        tok = _STATE.get("staff_token_fresh") or _STATE["staff_token"]
        r = requests.post(f"{BASE}/api/auth/change-password", headers=_h(tok),
                          json={"current_password": _STATE["staff_pw"], "new_password": "short"}, timeout=15)
        assert r.status_code == 422, r.text

    def test_change_password_success(self):
        tok = _STATE.get("staff_token_fresh") or _STATE["staff_token"]
        new_pw = "Staff-QA-Changed-2026!"
        r = requests.post(f"{BASE}/api/auth/change-password", headers=_h(tok),
                          json={"current_password": _STATE["staff_pw"], "new_password": new_pw}, timeout=15)
        assert r.status_code in (200, 204), r.text
        # login with new password
        r2 = requests.post(f"{BASE}/api/auth/login", json={"email": STAFF_EMAIL, "password": new_pw}, timeout=15)
        assert r2.status_code == 200, r2.text
        _STATE["staff_pw"] = new_pw


# ==================== CLEANUP ====================
def test_zzz_cleanup(owner_token, tenant_id):
    """Remove staff membership + device (rotate + deactivate + delete via ...) — best effort."""
    # Remove staff membership (owner can DELETE)
    uid = _STATE.get("staff_user_id")
    if uid:
        r = requests.delete(f"{BASE}/api/v1/tenants/{tenant_id}/members/{uid}", headers=_h(owner_token), timeout=15)
        assert r.status_code in (204, 404), r.text
    # Deactivate device (no delete API)
    did = _STATE.get("device_id")
    if did:
        requests.patch(f"{BASE}/api/v1/devices/{did}", headers=_h(owner_token), json={"is_active": False}, timeout=15)
    print(f"[cleanup] state: {_STATE}")
