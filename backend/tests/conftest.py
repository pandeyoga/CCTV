"""Test app on a temporary SQLite DB with seeded tenant/store/device/camera fixtures."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth import hash_password, issue_device_key  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base, Camera, DashboardUser, Device, Store, Tenant, TenantMembership  # noqa: E402


class Fixture:
    def __init__(self) -> None:
        self.ids: dict[str, object] = {}
        self.keys: dict[str, str] = {}


async def _seed(url: str) -> Fixture:
    fx = Fixture()
    db = Database(url)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with db.sessionmaker() as s:
        t1 = Tenant(name="Tenant A", contact_email="erpdevelopment212@hotmail.com")
        t2 = Tenant(name="Tenant B")
        s.add_all([t1, t2])
        await s.flush()
        st1 = Store(tenant_id=t1.id, name="Toko A", timezone="Asia/Jakarta")
        st2 = Store(tenant_id=t2.id, name="Toko B", timezone="UTC")
        s.add_all([st1, st2])
        await s.flush()
        k1, k2, k_inactive = issue_device_key(), issue_device_key(), issue_device_key()
        d1 = Device(tenant_id=t1.id, store_id=st1.id, name="dev-a", key_id=k1.key_id, secret_hash=k1.secret_hash, api_key_prefix=k1.prefix)
        d2 = Device(tenant_id=t2.id, store_id=st2.id, name="dev-b", key_id=k2.key_id, secret_hash=k2.secret_hash, api_key_prefix=k2.prefix)
        d3 = Device(tenant_id=t1.id, store_id=st1.id, name="dev-off", key_id=k_inactive.key_id, secret_hash=k_inactive.secret_hash,
                    api_key_prefix=k_inactive.prefix, is_active=False)
        s.add_all([d1, d2, d3])
        await s.flush()
        s.add_all([
            Camera(tenant_id=t1.id, store_id=st1.id, device_id=d1.id, external_id="cam-a", name="A door"),
            Camera(tenant_id=t2.id, store_id=st2.id, device_id=d2.id, external_id="cam-b", name="B door"),
        ])
        ua = DashboardUser(email="owner-a@example.com", password_hash=hash_password("correct-horse-battery"))
        ub = DashboardUser(email="owner-b@example.com", password_hash=hash_password("correct-horse-battery"))
        u_staff = DashboardUser(email="staff-a@example.com", password_hash=hash_password("correct-horse-battery"))
        u_admin = DashboardUser(email="admin@example.com", password_hash=hash_password("correct-horse-battery"), is_platform_admin=True)
        u_none = DashboardUser(email="nobody@example.com", password_hash=hash_password("correct-horse-battery"))
        u_off = DashboardUser(email="off@example.com", password_hash=hash_password("correct-horse-battery"), is_active=False)
        s.add_all([ua, ub, u_staff, u_admin, u_none, u_off])
        await s.flush()
        s.add_all([TenantMembership(user_id=ua.id, tenant_id=t1.id, role="owner"), TenantMembership(user_id=ub.id, tenant_id=t2.id, role="owner"),
                   TenantMembership(user_id=u_staff.id, tenant_id=t1.id, role="staff"),
                   TenantMembership(user_id=u_off.id, tenant_id=t1.id, role="owner")])
        await s.commit()
        fx.ids = {"store_a": st1.id, "store_b": st2.id, "device_a": d1.id, "device_b": d2.id, "tenant_a": t1.id, "tenant_b": t2.id,
                  "camera_a": None, "user_staff": u_staff.id, "user_a": ua.id, "user_b": ub.id}
        cam_a = (await s.execute(select(Camera).where(Camera.external_id == "cam-a"))).scalar_one()
        fx.ids["camera_a"] = cam_a.id
        fx.keys = {"a": k1.token, "b": k2.token, "inactive": k_inactive.token}
    await db.dispose()
    return fx


@pytest.fixture
def db_url(tmp_path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'test.sqlite3'}"


@pytest.fixture
def fx(db_url) -> Fixture:
    return asyncio.run(_seed(db_url))


JWT_SECRET = "test-secret-" + "x" * 40
PASSWORD = "correct-horse-battery"


def login(client, email: str, password: str = PASSWORD) -> dict:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def client(db_url, fx):
    settings = Settings(database_url=db_url, cors_origins=[], auto_create_schema=False, jwt_secret=JWT_SECRET, jwt_ttl_minutes=60)
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def auth_a(client):
    return login(client, "owner-a@example.com")


@pytest.fixture
def auth_b(client):
    return login(client, "owner-b@example.com")


@pytest.fixture
def auth_staff(client):
    return login(client, "staff-a@example.com")


@pytest.fixture
def auth_admin(client):
    return login(client, "admin@example.com")


@pytest.fixture
def client_auth_disabled(db_url, fx):
    settings = Settings(database_url=db_url, cors_origins=[], auto_create_schema=False, dashboard_auth="disabled")
    with TestClient(create_app(settings)) as c:
        yield c
