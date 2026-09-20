"""Operator-only provisioning (never an HTTP endpoint).

Usage:
  python -m app.seed --tenant "Demo Tenant" --contact-email owner@example.com \
      --store "Toko Pilot" --timezone Asia/Jakarta --camera cam-door-front --device dev-pilot-01

Idempotent for tenant/store/camera (get-or-create by name). A device key is issued only when the
device is created; it is printed ONCE and never stored.
"""
from __future__ import annotations

import argparse
import asyncio
import json

from sqlalchemy import select

from .auth import issue_device_key
from .config import get_settings
from .db import Database
from .models import Base, Camera, Device, Store, Tenant


async def seed(args: argparse.Namespace) -> dict:
    db = Database(get_settings().database_url)
    if args.create_schema:
        async with db.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    out: dict = {}
    async with db.sessionmaker() as s:
        tenant = (await s.execute(select(Tenant).where(Tenant.name == args.tenant))).scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(name=args.tenant, contact_email=args.contact_email)
            s.add(tenant)
            await s.flush()
        store = (await s.execute(select(Store).where(Store.tenant_id == tenant.id, Store.name == args.store))).scalar_one_or_none()
        if store is None:
            store = Store(tenant_id=tenant.id, name=args.store, timezone=args.timezone)
            s.add(store)
            await s.flush()
        device = (await s.execute(select(Device).where(Device.store_id == store.id, Device.name == args.device))).scalar_one_or_none()
        if device is None:
            key = issue_device_key()
            device = Device(tenant_id=tenant.id, store_id=store.id, name=args.device, key_id=key.key_id,
                            secret_hash=key.secret_hash, api_key_prefix=key.prefix)
            s.add(device)
            await s.flush()
            out["device_api_key_SHOW_ONCE"] = key.token
        camera = (await s.execute(select(Camera).where(Camera.store_id == store.id, Camera.external_id == args.camera))).scalar_one_or_none()
        if camera is None:
            camera = Camera(tenant_id=tenant.id, store_id=store.id, device_id=device.id, external_id=args.camera, name=args.camera)
            s.add(camera)
            await s.flush()
        await s.commit()
        out.update(tenant_id=str(tenant.id), store_id=str(store.id), device_id=str(device.id), camera_id=args.camera,
                   timezone=store.timezone)
    await db.dispose()
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tenant", required=True)
    p.add_argument("--contact-email", default=None)
    p.add_argument("--store", required=True)
    p.add_argument("--timezone", default="Asia/Jakarta")
    p.add_argument("--camera", required=True)
    p.add_argument("--device", required=True)
    p.add_argument("--create-schema", action="store_true", help="create tables if missing (dev only)")
    print(json.dumps(asyncio.run(seed(p.parse_args())), indent=2))


if __name__ == "__main__":
    main()
