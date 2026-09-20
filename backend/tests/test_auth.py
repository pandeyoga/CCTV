"""Finding 3: dashboard access is per-user, tenant-scoped, and never derived from request UUIDs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.auth import JWT_ALG
from conftest import JWT_SECRET, login
from test_ingest import auth, event

READ_PATHS = ("/summary", "/hourly", "/devices")


def _paths(store_id) -> list[str]:
    return ["/api/v1/stores"] + [f"/api/v1/stores/{store_id}{p}" for p in READ_PATHS]


def test_unauthenticated_rejected_on_every_read_endpoint(client, fx):
    for p in _paths(fx.ids["store_a"]):
        r = client.get(p)
        assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer", p
    assert client.get("/api/auth/me").status_code == 401


def test_login_failures_are_uniform_401(client, fx):
    assert client.post("/api/auth/login", json={"email": "owner-a@example.com", "password": "wrong-password"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "correct-horse-battery"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "off@example.com", "password": "correct-horse-battery"}).status_code == 401  # inactive
    assert client.post("/api/auth/login", json={"email": "not-an-email", "password": "x"}).status_code == 422
    assert client.post("/api/auth/login", json={"email": "owner-a@example.com", "password": "x", "tenant_id": "spoof"}).status_code == 422


def test_login_returns_token_and_memberships_only(client, fx):
    r = client.post("/api/auth/login", json={"email": "Owner-A@Example.com", "password": "correct-horse-battery"})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 3600
    assert body["user"]["email"] == "owner-a@example.com"
    assert body["user"]["tenant_ids"] == [str(fx.ids["tenant_a"])]
    assert "password" not in str(body) and "hash" not in str(body)
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}).json()
    assert me["tenant_ids"] == [str(fx.ids["tenant_a"])]


def test_tenant_a_reads_own_store_only(client, fx, auth_a):
    for p in _paths(fx.ids["store_a"])[1:]:
        assert client.get(p, headers=auth_a).status_code == 200, p
    stores = client.get("/api/v1/stores", headers=auth_a).json()
    assert [s["name"] for s in stores] == ["Toko A"]
    assert all(s["tenant_id"] == str(fx.ids["tenant_a"]) for s in stores)


def test_tenant_a_cannot_read_tenant_b_store_by_known_uuid(client, fx, auth_a, auth_b):
    # Tenant B's data exists and is readable by B ...
    client.post("/api/v1/events/batch", json={"events": [event(camera_id="cam-b")]}, headers=auth(fx.keys["b"]))
    assert client.get(f"/api/v1/stores/{fx.ids['store_b']}/summary?date=2026-06-01", headers=auth_b).json()["enter"] == 1
    # ... but A gets 404 (indistinguishable from "does not exist") on every endpoint, even with the real UUID.
    for p in _paths(fx.ids["store_b"])[1:]:
        r = client.get(p, headers=auth_a)
        assert r.status_code == 404, p
        assert "Toko B" not in r.text and "enter" not in r.text


def test_user_without_memberships_sees_nothing(client, fx):
    h = login(client, "nobody@example.com")
    assert client.get("/api/v1/stores", headers=h).json() == []
    assert client.get(f"/api/v1/stores/{fx.ids['store_a']}/summary", headers=h).status_code == 404


def _token(payload: dict, secret: str = JWT_SECRET) -> dict:
    return {"Authorization": f"Bearer {jwt.encode(payload, secret, algorithm=JWT_ALG)}"}


def _claims(fx, **over) -> dict:
    now = datetime.now(timezone.utc)
    base = {"sub": "00000000-0000-0000-0000-000000000000", "typ": "dashboard",
            "iat": int(now.timestamp()), "exp": int((now + timedelta(hours=1)).timestamp())}
    base.update(over)
    return base


def test_expired_invalid_and_foreign_tokens_rejected(client, fx, auth_a):
    r = client.post("/api/auth/login", json={"email": "owner-a@example.com", "password": "correct-horse-battery"})
    real = jwt.decode(r.json()["access_token"], JWT_SECRET, algorithms=[JWT_ALG])
    past = int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp())
    cases = {
        "expired": _token(_claims(fx, sub=real["sub"], exp=past)),
        "wrong secret": _token(_claims(fx, sub=real["sub"]), secret="another-secret-" + "y" * 40),
        "wrong typ": _token(_claims(fx, sub=real["sub"], typ="device")),
        "missing exp": _token({"sub": real["sub"], "typ": "dashboard"}),
        "unknown user": _token(_claims(fx)),
        "garbage": {"Authorization": "Bearer not.a.jwt"},
        "basic scheme": {"Authorization": "Basic b3duZXItYUBleGFtcGxlLmNvbTp4"},
    }
    for name, h in cases.items():
        r = client.get("/api/v1/stores", headers=h)
        assert r.status_code == 401, name
    assert client.get("/api/v1/stores", headers=auth_a).status_code == 200  # sanity: the real token still works


def test_alg_none_token_rejected(client, fx):
    r = client.post("/api/auth/login", json={"email": "owner-a@example.com", "password": "correct-horse-battery"})
    real = jwt.decode(r.json()["access_token"], JWT_SECRET, algorithms=[JWT_ALG])
    unsigned = jwt.encode(_claims(fx, sub=real["sub"]), None, algorithm="none")  # type: ignore[arg-type]
    assert client.get("/api/v1/stores", headers={"Authorization": f"Bearer {unsigned}"}).status_code == 401


def test_deactivated_user_token_stops_working(client, fx, db_url):
    """Authorization is loaded from the DB per request, so revocation is immediate (no token blacklist needed)."""
    import asyncio
    from sqlalchemy import update
    from app.db import Database
    from app.models import DashboardUser

    h = login(client, "owner-a@example.com")
    assert client.get("/api/v1/stores", headers=h).status_code == 200

    async def deactivate():
        db = Database(db_url)
        async with db.sessionmaker() as s:
            await s.execute(update(DashboardUser).where(DashboardUser.email == "owner-a@example.com").values(is_active=False))
            await s.commit()
        await db.dispose()

    asyncio.run(deactivate())
    assert client.get("/api/v1/stores", headers=h).status_code == 401


def test_device_key_is_not_a_dashboard_login_and_vice_versa(client, fx, auth_a):
    assert client.get("/api/v1/stores", headers=auth(fx.keys["a"])).status_code == 401
    assert client.get(f"/api/v1/stores/{fx.ids['store_a']}/devices", headers=auth(fx.keys["a"])).status_code == 401
    # a user JWT cannot ingest events
    assert client.post("/api/v1/events/batch", json={"events": [event()]}, headers=auth_a).status_code == 401
    assert client.post("/api/auth/login", json={"email": "owner-a@example.com", "password": fx.keys["a"]}).status_code == 401


def test_login_throttle_locks_after_repeated_failures(client, fx):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": "owner-a@example.com", "password": "nope-nope-nope"}).status_code == 401
    # even the correct password is refused while locked; another account is unaffected
    assert client.post("/api/auth/login", json={"email": "owner-a@example.com", "password": "correct-horse-battery"}).status_code == 429
    assert client.post("/api/auth/login", json={"email": "owner-b@example.com", "password": "correct-horse-battery"}).status_code == 200


def test_auth_disabled_is_explicit_dev_mode_only(client_auth_disabled, fx):
    c = client_auth_disabled
    assert {s["name"] for s in c.get("/api/v1/stores").json()} == {"Toko A", "Toko B"}
    assert c.post("/api/auth/login", json={"email": "owner-a@example.com", "password": "correct-horse-battery"}).status_code == 404


def test_settings_refuse_missing_jwt_secret(monkeypatch):
    from app.config import get_settings
    import pytest

    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("DASHBOARD_AUTH", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        get_settings()  # missing config fails fast; never silently opens the dashboard
    monkeypatch.setenv("JWT_SECRET", "too-short")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        get_settings()
    monkeypatch.setenv("DASHBOARD_AUTH", "maybe")
    with pytest.raises(RuntimeError, match="DASHBOARD_AUTH"):
        get_settings()


def test_health_stays_public(client):
    assert client.get("/api/health").status_code == 200
