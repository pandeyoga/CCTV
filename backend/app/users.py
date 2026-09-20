"""Operator-only dashboard user provisioning (never an HTTP endpoint; no public signup).

  python -m app.users create --email owner@example.com --tenant "Pilot Tenant" [--password-env DASHBOARD_PASSWORD]
  python -m app.users grant  --email owner@example.com --tenant "Other Tenant"
  python -m app.users set-password --email owner@example.com [--password-env DASHBOARD_PASSWORD]
  python -m app.users list

Passwords are read from the env var named by --password-env (default DASHBOARD_PASSWORD) or prompted;
they are never accepted as a CLI argument (shell history) and never printed.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os

from sqlalchemy import select

from .auth import hash_password
from .config import get_settings
from .db import Database
from .models import DashboardUser, Tenant, TenantMembership


def _password(args: argparse.Namespace) -> str:
    pw = os.environ.get(args.password_env) or getpass.getpass("Password: ")
    if len(pw) < 10:
        raise SystemExit("password must be at least 10 characters")
    return pw


async def _tenant(s, name: str) -> Tenant:
    t = (await s.execute(select(Tenant).where(Tenant.name == name))).scalar_one_or_none()
    if t is None:
        raise SystemExit(f"tenant not found: {name!r}")
    return t


async def _user(s, email: str) -> DashboardUser:
    u = (await s.execute(select(DashboardUser).where(DashboardUser.email == email.lower()))).scalar_one_or_none()
    if u is None:
        raise SystemExit(f"user not found: {email!r}")
    return u


async def seed_platform_admin(s, email: str, password: str) -> DashboardUser:
    """Idempotent: create the platform admin, or re-sync its password/flag when the env changed (ADR-024)."""
    from .auth import verify_password
    user = (await s.execute(select(DashboardUser).where(DashboardUser.email == email))).scalar_one_or_none()
    if user is None:
        user = DashboardUser(email=email, password_hash=hash_password(password), is_platform_admin=True)
        s.add(user)
    else:
        if not verify_password(password, user.password_hash):
            user.password_hash = hash_password(password)
        user.is_platform_admin = True
        user.is_active = True
    await s.commit()
    return user


async def _grant(s, user: DashboardUser, tenant: Tenant) -> bool:
    exists = (await s.execute(select(TenantMembership).where(TenantMembership.user_id == user.id,
                                                              TenantMembership.tenant_id == tenant.id))).scalar_one_or_none()
    if exists:
        return False
    s.add(TenantMembership(user_id=user.id, tenant_id=tenant.id, role="owner"))  # CLI-created users are tenant owners
    return True


async def run(args: argparse.Namespace) -> dict:
    db = Database(get_settings().database_url)
    out: dict = {}
    try:
        async with db.sessionmaker() as s:
            if args.cmd == "create":
                email = args.email.lower()
                if (await s.execute(select(DashboardUser).where(DashboardUser.email == email))).scalar_one_or_none():
                    raise SystemExit(f"user already exists: {email}")
                tenant = await _tenant(s, args.tenant)
                user = DashboardUser(email=email, password_hash=hash_password(_password(args)))
                s.add(user)
                await s.flush()
                await _grant(s, user, tenant)
                out = {"user_id": str(user.id), "email": email, "tenants": [tenant.name]}
            elif args.cmd == "grant":
                user, tenant = await _user(s, args.email), await _tenant(s, args.tenant)
                out = {"email": user.email, "granted": await _grant(s, user, tenant), "tenant": tenant.name}
            elif args.cmd == "set-password":
                user = await _user(s, args.email)
                user.password_hash = hash_password(_password(args))
                out = {"email": user.email, "password_updated": True}
            elif args.cmd == "list":
                rows = (await s.execute(select(DashboardUser).order_by(DashboardUser.created_at))).scalars().all()
                out = {"users": []}
                for u in rows:
                    tids = (await s.execute(select(TenantMembership.tenant_id).where(TenantMembership.user_id == u.id))).scalars()
                    out["users"].append({"email": u.email, "is_active": u.is_active, "tenant_ids": [str(t) for t in tids]})
            await s.commit()
    finally:
        await db.dispose()
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("create", "grant", "set-password"):
        sp = sub.add_parser(name)
        sp.add_argument("--email", required=True)
        if name != "set-password":
            sp.add_argument("--tenant", required=True)
        sp.add_argument("--password-env", default="DASHBOARD_PASSWORD")
    sub.add_parser("list")
    print(json.dumps(asyncio.run(run(p.parse_args())), indent=2))


if __name__ == "__main__":
    main()
