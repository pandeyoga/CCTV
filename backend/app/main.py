from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from .alerts import evaluate
from .config import Settings, get_settings
from .db import Database
from .models import Base, Tenant
from .auth import LoginThrottle
from .routers import alerts, auth, camera_config, devices, events, manage, reports, stores, zones
from .telegram import notify_pending
from .users import seed_platform_admin
from sqlalchemy import select

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("alerts")


async def alert_loop(db: Database, interval_s: int, telegram_token: str | None) -> None:
    """Evaluate alert rules for every tenant so incidents are recorded even when no dashboard is open (ADR-028),
    then push new/resolved incidents to Telegram (ADR-029)."""
    while True:
        await asyncio.sleep(interval_s)
        try:
            async with db.sessionmaker() as s:
                tenant_ids = list((await s.execute(select(Tenant.id))).scalars())
                if tenant_ids:
                    await evaluate(s, tenant_ids, datetime.now(timezone.utc))
                    await notify_pending(s, telegram_token)
        except Exception:  # keep the loop alive; the next tick retries
            log.exception("alert evaluation failed")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings.database_url)
        if settings.auto_create_schema:  # dev/preview only; production uses `alembic upgrade head`
            async with db.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        if settings.admin_email and settings.admin_password:
            async with db.sessionmaker() as s:
                await seed_platform_admin(s, settings.admin_email, settings.admin_password)
        app.state.db = db
        app.state.settings = settings
        app.state.login_throttle = LoginThrottle()
        task = asyncio.create_task(alert_loop(db, settings.alert_eval_interval_s, settings.telegram_bot_token)) if settings.alert_eval_interval_s > 0 else None
        try:
            yield
        finally:
            if task:
                task.cancel()
            await db.dispose()

    app = FastAPI(title="People Counter API", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins or ["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(auth.router)
    app.include_router(events.router)
    app.include_router(devices.router)
    app.include_router(stores.router)
    app.include_router(manage.router)
    app.include_router(reports.router)
    app.include_router(alerts.router)
    app.include_router(camera_config.router)
    app.include_router(zones.router)

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app
