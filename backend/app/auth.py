"""Two separate authentication mechanisms:

1. Device API key `dk_<key_id>.<secret>` (ingest + heartbeat). DB stores sha256(secret); constant-time compare.
   Tenant/store identity is derived from the authenticated Device row — never from the request body.
2. Dashboard users: email + bcrypt password -> short-lived HS256 JWT (PyJWT) with `typ: "dashboard"`.
   Authorization = tenant memberships loaded from the DB on every request (revocable), never from the token
   alone and never from UUIDs in the request. A device key is not a JWT and can never pass `require_user`.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Annotated, Mapping
from uuid import UUID

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import DashboardUser, Device, TenantMembership

_bearer = HTTPBearer(auto_error=False)
_DUMMY_HASH = hashlib.sha256(b"unusable-dummy-value").hexdigest()
_DUMMY_BCRYPT = bcrypt.hashpw(b"unusable-dummy-password", bcrypt.gensalt(rounds=4))
TOKEN_PREFIX = "dk_"
JWT_ALG = "HS256"
JWT_TYP = "dashboard"
LOCKOUT_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60


# ----------------------------------------------------------------------------- device keys
@dataclass(frozen=True)
class IssuedKey:
    token: str  # show once, never stored
    key_id: str
    secret_hash: str
    prefix: str


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def issue_device_key() -> IssuedKey:
    key_id = secrets.token_urlsafe(9)
    secret = secrets.token_urlsafe(32)
    token = f"{TOKEN_PREFIX}{key_id}.{secret}"
    return IssuedKey(token=token, key_id=key_id, secret_hash=digest(secret), prefix=token[:12])


def _unauthorized(msg: str = "Invalid device API key") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, msg, headers={"WWW-Authenticate": "Bearer"})


def split_token(token: str) -> tuple[str, str] | None:
    if not token.startswith(TOKEN_PREFIX) or "." not in token:
        return None
    key_id, secret = token[len(TOKEN_PREFIX):].split(".", 1)
    return (key_id, secret) if key_id and secret else None


async def get_session(request: Request) -> AsyncSession:
    async for s in request.app.state.db.session():
        yield s


async def require_device(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Device:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    parts = split_token(credentials.credentials)
    if parts is None:
        raise _unauthorized()
    key_id, presented = parts
    device = (await session.execute(select(Device).where(Device.key_id == key_id))).scalar_one_or_none()
    stored = device.secret_hash if device else _DUMMY_HASH
    if not secrets.compare_digest(stored, digest(presented)) or device is None:
        raise _unauthorized()
    if not device.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Device is inactive")
    return device


# ----------------------------------------------------------------------------- dashboard users
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    stored = password_hash.encode("utf-8") if password_hash else _DUMMY_BCRYPT
    ok = bcrypt.checkpw(password.encode("utf-8"), stored)
    return ok and password_hash is not None


def create_access_token(user: DashboardUser, secret: str, ttl_minutes: int, now: datetime | None = None) -> tuple[str, int]:
    now = now or datetime.now(timezone.utc)
    exp = now + timedelta(minutes=ttl_minutes)
    payload = {"sub": str(user.id), "email": user.email, "typ": JWT_TYP, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    return jwt.encode(payload, secret, algorithm=JWT_ALG), int((exp - now).total_seconds())


def decode_access_token(token: str, secret: str) -> UUID:
    try:
        payload = jwt.decode(token, secret, algorithms=[JWT_ALG], options={"require": ["exp", "sub", "typ"]})
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Session expired")
    except jwt.InvalidTokenError:
        raise _unauthorized("Not authenticated")
    if payload.get("typ") != JWT_TYP:
        raise _unauthorized("Not authenticated")
    try:
        return UUID(payload["sub"])
    except (ValueError, KeyError):
        raise _unauthorized("Not authenticated")


@dataclass(frozen=True)
class CurrentUser:
    user_id: UUID
    email: str
    tenant_ids: frozenset[UUID]
    roles: Mapping[UUID, str] = field(default_factory=dict)  # tenant_id -> owner | staff
    is_platform_admin: bool = False

    def can_manage(self, tenant_id: UUID) -> bool:
        return self.is_platform_admin or self.roles.get(tenant_id) == "owner"


async def load_current_user(session: AsyncSession, user_id: UUID) -> CurrentUser | None:
    user = await session.get(DashboardUser, user_id)
    if user is None or not user.is_active:
        return None
    if user.is_platform_admin:  # every tenant, re-read per request so new tenants are visible immediately
        from .models import Tenant
        ids = frozenset((await session.execute(select(Tenant.id))).scalars())
        return CurrentUser(user_id=user.id, email=user.email, tenant_ids=ids, roles={}, is_platform_admin=True)
    rows = await session.execute(select(TenantMembership.tenant_id, TenantMembership.role).where(TenantMembership.user_id == user.id))
    roles = {tid: role for tid, role in rows.all()}
    return CurrentUser(user_id=user.id, email=user.email, tenant_ids=frozenset(roles), roles=roles)


def forbidden(msg: str = "Not permitted") -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, msg)


async def require_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CurrentUser:
    settings = request.app.state.settings
    if settings.dashboard_auth == "disabled":  # explicit local-dev mode: every tenant readable
        from .models import Tenant
        ids = frozenset((await session.execute(select(Tenant.id))).scalars())
        return CurrentUser(user_id=UUID(int=0), email="dev@localhost", tenant_ids=ids, is_platform_admin=True)
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Not authenticated")
    user_id = decode_access_token(credentials.credentials, settings.jwt_secret)
    user = await load_current_user(session, user_id)
    if user is None:
        raise _unauthorized("Not authenticated")
    return user


async def require_platform_admin(user: Annotated[CurrentUser, Depends(require_user)]) -> CurrentUser:
    if not user.is_platform_admin:
        raise forbidden("Platform admin only")
    return user


class LoginThrottle:
    """In-memory brute-force limiter keyed by (client ip, email): LOCKOUT_ATTEMPTS failures -> LOCKOUT_SECONDS."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._failures: dict[str, list[float]] = defaultdict(list)

    def is_locked(self, key: str) -> bool:
        cutoff = self._clock() - LOCKOUT_SECONDS
        self._failures[key] = [t for t in self._failures[key] if t > cutoff]
        return len(self._failures[key]) >= LOCKOUT_ATTEMPTS

    def record_failure(self, key: str) -> None:
        self._failures[key].append(self._clock())

    def clear(self, key: str) -> None:
        self._failures.pop(key, None)
