"""ADR-024: self-service management is role-scoped. Owner A can never touch tenant B; staff is read-only;
platform admin sees everything; device keys are shown once and old keys die on rotation."""
from __future__ import annotations

from conftest import login
from test_ingest import auth, event

A_STORE = "store_a"


def _post(client, path, body, headers, code=201):
    r = client.post(path, json=body, headers=headers)
    assert r.status_code == code, (path, r.status_code, r.text)
    return r.json() if r.content else None


def test_login_exposes_roles_and_platform_admin_flag(client, fx, auth_a, auth_staff, auth_admin):
    me_a = client.get("/api/auth/me", headers=auth_a).json()
    assert me_a["is_platform_admin"] is False
    assert me_a["memberships"] == [{"tenant_id": str(fx.ids["tenant_a"]), "tenant_name": "Tenant A", "role": "owner"}]
    assert client.get("/api/auth/me", headers=auth_staff).json()["memberships"][0]["role"] == "staff"
    me_admin = client.get("/api/auth/me", headers=auth_admin).json()
    assert me_admin["is_platform_admin"] is True
    assert {m["tenant_name"] for m in me_admin["memberships"]} == {"Tenant A", "Tenant B"}
    assert all(m["role"] == "platform_admin" for m in me_admin["memberships"])


def test_tenant_list_is_scoped_and_only_admin_creates(client, fx, auth_a, auth_admin, auth_staff):
    assert [t["name"] for t in client.get("/api/v1/tenants", headers=auth_a).json()] == ["Tenant A"]
    assert client.post("/api/v1/tenants", json={"name": "Tenant C"}, headers=auth_a).status_code == 403
    assert client.post("/api/v1/tenants", json={"name": "Tenant C"}, headers=auth_staff).status_code == 403
    t = _post(client, "/api/v1/tenants", {"name": "Tenant C", "contact_email": "c@example.com"}, auth_admin)
    assert t["role"] == "platform_admin" and t["store_count"] == 0
    assert client.post("/api/v1/tenants", json={"name": "Tenant C"}, headers=auth_admin).status_code == 409
    assert client.patch(f"/api/v1/tenants/{t['tenant_id']}", json={"name": "Tenant C2"}, headers=auth_admin).json()["name"] == "Tenant C2"
    # the new tenant is visible to the admin immediately (memberships re-read per request)
    assert "Tenant C2" in {x["name"] for x in client.get("/api/v1/tenants", headers=auth_admin).json()}


def test_owner_creates_store_in_own_tenant_only(client, fx, auth_a, auth_staff, auth_admin):
    body = {"tenant_id": str(fx.ids["tenant_a"]), "name": "Toko A2", "timezone": "Asia/Makassar"}
    st = _post(client, "/api/v1/stores", body, auth_a)
    assert st["timezone"] == "Asia/Makassar"
    assert client.post("/api/v1/stores", json=body, headers=auth_a).status_code == 409
    assert client.post("/api/v1/stores", json={**body, "name": "x", "timezone": "Mars/Olympus"}, headers=auth_a).status_code == 422
    assert client.post("/api/v1/stores", json={**body, "tenant_id": str(fx.ids["tenant_b"])}, headers=auth_a).status_code == 404
    assert client.post("/api/v1/stores", json={**body, "name": "Toko staff"}, headers=auth_staff).status_code == 403
    assert client.patch(f"/api/v1/stores/{st['store_id']}", json={"name": "Toko A3"}, headers=auth_a).json()["name"] == "Toko A3"
    assert client.patch(f"/api/v1/stores/{fx.ids['store_b']}", json={"name": "hack"}, headers=auth_a).status_code == 404
    assert client.patch(f"/api/v1/stores/{fx.ids['store_b']}", json={"name": "Toko B2"}, headers=auth_admin).status_code == 200
    names = {s["name"] for s in client.get("/api/v1/stores", headers=auth_a).json()}
    assert names == {"Toko A", "Toko A3"}


def test_device_key_shown_once_and_rotation_kills_old_key(client, fx, auth_a, auth_staff):
    out = _post(client, f"/api/v1/stores/{fx.ids[A_STORE]}/devices", {"name": "dev-new"}, auth_a)
    key = out["api_key_show_once"]
    assert key.startswith("dk_") and out["device"]["name"] == "dev-new" and out["device"]["is_active"] is True
    # key works for heartbeat; but it is no longer retrievable from any read endpoint
    hb = {"schema_version": 1, "sent_at": "2026-06-01T00:00:00Z", "source_status": "ok", "last_frame_age_s": 1.0,
          "pending_events": 0, "frames_processed": 10, "tracking_session_id": 0, "agent_version": "t"}
    assert client.post("/api/v1/devices/heartbeat", json=hb, headers=auth(key)).status_code == 200
    assert key not in client.get("/api/v1/devices", headers=auth_a).text
    assert client.post(f"/api/v1/stores/{fx.ids[A_STORE]}/devices", json={"name": "dev-new"}, headers=auth_a).status_code == 409
    assert client.post(f"/api/v1/stores/{fx.ids[A_STORE]}/devices", json={"name": "s"}, headers=auth_staff).status_code == 403
    assert client.post(f"/api/v1/stores/{fx.ids['store_b']}/devices", json={"name": "s"}, headers=auth_a).status_code == 404

    dev_id = out["device"]["device_id"]
    rotated = client.post(f"/api/v1/devices/{dev_id}/rotate-key", headers=auth_a).json()
    assert rotated["api_key_show_once"] != key
    assert client.post("/api/v1/devices/heartbeat", json=hb, headers=auth(key)).status_code == 401
    assert client.post("/api/v1/devices/heartbeat", json=hb, headers=auth(rotated["api_key_show_once"])).status_code == 200

    assert client.patch(f"/api/v1/devices/{dev_id}", json={"is_active": False}, headers=auth_a).json()["is_active"] is False
    assert client.post("/api/v1/devices/heartbeat", json=hb, headers=auth(rotated["api_key_show_once"])).status_code == 403
    assert client.post(f"/api/v1/devices/{fx.ids['device_b']}/rotate-key", headers=auth_a).status_code == 404
    assert client.patch(f"/api/v1/devices/{fx.ids['device_b']}", json={"name": "x"}, headers=auth_a).status_code == 404


def test_camera_crud_scoped_and_protected_by_events(client, fx, auth_a, auth_b, auth_staff):
    store_a = fx.ids[A_STORE]
    cams = client.get(f"/api/v1/stores/{store_a}/cameras", headers=auth_staff).json()  # staff may read
    assert [c["external_id"] for c in cams] == ["cam-a"]
    assert client.get(f"/api/v1/stores/{fx.ids['store_b']}/cameras", headers=auth_a).status_code == 404
    new = _post(client, f"/api/v1/stores/{store_a}/cameras", {"external_id": "cam-side", "name": "Pintu samping", "device_id": str(fx.ids["device_a"])}, auth_a)
    assert new["device_id"] == str(fx.ids["device_a"])
    assert client.post(f"/api/v1/stores/{store_a}/cameras", json={"external_id": "cam-side", "name": "dup"}, headers=auth_a).status_code == 409
    assert client.post(f"/api/v1/stores/{store_a}/cameras", json={"external_id": "bad id", "name": "x"}, headers=auth_a).status_code == 422
    # a device from another store cannot be assigned
    assert client.post(f"/api/v1/stores/{store_a}/cameras", json={"external_id": "c2", "name": "x", "device_id": str(fx.ids["device_b"])}, headers=auth_a).status_code == 422
    assert client.patch(f"/api/v1/cameras/{new['camera_id']}", json={"name": "Samping", "clear_device": True}, headers=auth_a).json()["device_id"] is None
    assert client.patch(f"/api/v1/cameras/{new['camera_id']}", json={"name": "x"}, headers=auth_b).status_code == 404
    assert client.delete(f"/api/v1/cameras/{new['camera_id']}", headers=auth_staff).status_code == 403
    assert client.delete(f"/api/v1/cameras/{new['camera_id']}", headers=auth_a).status_code == 204
    # camera with events cannot be deleted
    client.post("/api/v1/events/batch", json={"events": [event(camera_id="cam-a")]}, headers=auth(fx.keys["a"]))
    assert client.delete(f"/api/v1/cameras/{fx.ids['camera_a']}", headers=auth_a).status_code == 409


def test_member_management_scoped_to_owned_tenant(client, fx, auth_a, auth_b, auth_staff):
    ta, tb = fx.ids["tenant_a"], fx.ids["tenant_b"]
    members = client.get(f"/api/v1/tenants/{ta}/members", headers=auth_a).json()
    assert {(m["email"], m["role"]) for m in members} == {("owner-a@example.com", "owner"), ("staff-a@example.com", "staff"), ("off@example.com", "owner")}
    assert client.get(f"/api/v1/tenants/{ta}/members", headers=auth_staff).status_code == 403
    assert client.get(f"/api/v1/tenants/{tb}/members", headers=auth_a).status_code == 404
    # new user requires a password; then can log in and is read-only
    assert client.post(f"/api/v1/tenants/{ta}/members", json={"email": "kasir@example.com", "role": "staff"}, headers=auth_a).status_code == 422
    m = _post(client, f"/api/v1/tenants/{ta}/members", {"email": "Kasir@Example.com", "role": "staff", "password": "kasir-password-1"}, auth_a)
    assert m["email"] == "kasir@example.com" and m["role"] == "staff"
    h = login(client, "kasir@example.com", "kasir-password-1")
    assert [s["name"] for s in client.get("/api/v1/stores", headers=h).json()] == ["Toko A"]
    assert client.post("/api/v1/stores", json={"tenant_id": str(ta), "name": "n", "timezone": "UTC"}, headers=h).status_code == 403
    # existing user from another tenant can be granted without a password; duplicates -> 409
    assert client.post(f"/api/v1/tenants/{ta}/members", json={"email": "owner-b@example.com", "role": "staff"}, headers=auth_a).status_code == 201
    assert client.post(f"/api/v1/tenants/{ta}/members", json={"email": "owner-b@example.com", "role": "staff"}, headers=auth_a).status_code == 409
    assert client.post(f"/api/v1/tenants/{ta}/members", json={"email": "admin@example.com", "role": "staff"}, headers=auth_a).status_code == 409
    # promote, self-guard, remove
    assert client.patch(f"/api/v1/tenants/{ta}/members/{m['user_id']}", json={"role": "owner"}, headers=auth_a).json()["role"] == "owner"
    assert client.patch(f"/api/v1/tenants/{ta}/members/{fx.ids['user_a']}", json={"role": "staff"}, headers=auth_a).status_code == 409
    assert client.delete(f"/api/v1/tenants/{ta}/members/{fx.ids['user_a']}", headers=auth_a).status_code == 409
    assert client.delete(f"/api/v1/tenants/{ta}/members/{fx.ids['user_b']}", headers=auth_a).status_code == 204
    assert client.delete(f"/api/v1/tenants/{ta}/members/{fx.ids['user_b']}", headers=auth_a).status_code == 404
    # owner B cannot see tenant A's member even by known user id
    assert client.post(f"/api/v1/users/{m['user_id']}/reset-password", json={"password": "hijacked-pass-1"}, headers=auth_b).status_code == 404
    # owner A resets kasir's password; old password stops working
    assert client.post(f"/api/v1/users/{m['user_id']}/reset-password", json={"password": "kasir-password-2"}, headers=auth_a).status_code == 204
    assert client.post("/api/auth/login", json={"email": "kasir@example.com", "password": "kasir-password-1"}).status_code == 401
    login(client, "kasir@example.com", "kasir-password-2")


def test_platform_admin_user_admin_and_self_deactivation_guard(client, fx, auth_a, auth_admin):
    assert client.get("/api/v1/users", headers=auth_a).status_code == 403
    users = client.get("/api/v1/users", headers=auth_admin).json()
    staff = next(u for u in users if u["email"] == "staff-a@example.com")
    assert staff["memberships"] == [{"tenant_id": str(fx.ids["tenant_a"]), "tenant_name": "Tenant A", "role": "staff"}]
    admin = next(u for u in users if u["email"] == "admin@example.com")
    assert admin["is_platform_admin"] is True and admin["memberships"] == []
    # owner cannot reset a platform admin's password
    assert client.post(f"/api/v1/users/{admin['user_id']}/reset-password", json={"password": "hijacked-pass-1"}, headers=auth_a).status_code == 404
    # admin deactivates staff -> immediate 401 for that user
    h_staff = login(client, "staff-a@example.com")
    assert client.patch(f"/api/v1/users/{staff['user_id']}", json={"is_active": False}, headers=auth_admin).json()["is_active"] is False
    assert client.get("/api/v1/stores", headers=h_staff).status_code == 401
    assert client.patch(f"/api/v1/users/{staff['user_id']}", json={"is_active": False}, headers=auth_a).status_code == 403
    assert client.patch(f"/api/v1/users/{admin['user_id']}", json={"is_active": False}, headers=auth_admin).status_code == 409


def test_change_own_password(client, fx, auth_a):
    assert client.post("/api/auth/change-password", json={"current_password": "wrong", "new_password": "new-password-123"}, headers=auth_a).status_code == 403
    assert client.post("/api/auth/change-password", json={"current_password": "correct-horse-battery", "new_password": "short"}, headers=auth_a).status_code == 422
    assert client.post("/api/auth/change-password", json={"current_password": "correct-horse-battery", "new_password": "new-password-123"}, headers=auth_a).status_code == 204
    assert client.post("/api/auth/login", json={"email": "owner-a@example.com", "password": "correct-horse-battery"}).status_code == 401
    login(client, "owner-a@example.com", "new-password-123")


def test_platform_admin_seeded_from_env(db_url, fx):
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app
    from conftest import JWT_SECRET
    settings = Settings(database_url=db_url, cors_origins=[], auto_create_schema=False, jwt_secret=JWT_SECRET,
                        admin_email="root@example.com", admin_password="root-password-1")
    with TestClient(create_app(settings)) as c:
        h = login(c, "root@example.com", "root-password-1")
        assert c.get("/api/auth/me", headers=h).json()["is_platform_admin"] is True
    # second start with a changed password re-syncs it (idempotent, no duplicate user)
    settings2 = Settings(database_url=db_url, cors_origins=[], auto_create_schema=False, jwt_secret=JWT_SECRET,
                         admin_email="root@example.com", admin_password="root-password-2")
    with TestClient(create_app(settings2)) as c:
        assert c.post("/api/auth/login", json={"email": "root@example.com", "password": "root-password-1"}).status_code == 401
        h = login(c, "root@example.com", "root-password-2")
        assert sum(1 for u in c.get("/api/v1/users", headers=h).json() if u["email"] == "root@example.com") == 1
