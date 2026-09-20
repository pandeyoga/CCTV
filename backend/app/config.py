"""Environment-only configuration. Missing required values fail fast."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


AUTH_MODES = ("required", "disabled")


@dataclass(frozen=True)
class Settings:
    database_url: str
    cors_origins: list[str]
    auto_create_schema: bool
    jwt_secret: str | None = None
    jwt_ttl_minutes: int = 720
    dashboard_auth: str = "required"  # "disabled" only for explicit local development (never a fallback)
    admin_email: str | None = None  # ADMIN_EMAIL + ADMIN_PASSWORD -> platform admin seeded at startup (ADR-024)
    admin_password: str | None = None
    alert_eval_interval_s: int = 0  # background alert evaluation loop; 0 = only on read (tests); env default 60 (ADR-028)


def get_settings() -> Settings:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required (e.g. postgresql+asyncpg://... or sqlite+aiosqlite:///...)")
    auth_mode = os.environ.get("DASHBOARD_AUTH", "required").lower()
    if auth_mode not in AUTH_MODES:
        raise RuntimeError(f"DASHBOARD_AUTH must be one of {AUTH_MODES}")
    secret = os.environ.get("JWT_SECRET") or None
    if auth_mode == "required" and (secret is None or len(secret) < 32):
        raise RuntimeError("JWT_SECRET (>= 32 chars) is required; set DASHBOARD_AUTH=disabled only for local development")
    admin_email, admin_password = os.environ.get("ADMIN_EMAIL") or None, os.environ.get("ADMIN_PASSWORD") or None
    if bool(admin_email) != bool(admin_password):
        raise RuntimeError("ADMIN_EMAIL and ADMIN_PASSWORD must be set together")
    if admin_password is not None and len(admin_password) < 10:
        raise RuntimeError("ADMIN_PASSWORD must be at least 10 characters")
    return Settings(
        database_url=url,
        cors_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()],
        auto_create_schema=os.environ.get("AUTO_CREATE_SCHEMA", "false").lower() == "true",
        jwt_secret=secret,
        jwt_ttl_minutes=int(os.environ.get("JWT_TTL_MINUTES", "720")),
        dashboard_auth=auth_mode,
        admin_email=admin_email.lower() if admin_email else None,
        admin_password=admin_password,
        alert_eval_interval_s=int(os.environ.get("ALERT_EVAL_INTERVAL_S", "60")),
    )
