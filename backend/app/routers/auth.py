"""POST /api/auth/login, GET /api/auth/me — dashboard user sessions (JWT Bearer)."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import CurrentUser, create_access_token, get_session, hash_password, load_current_user, require_user, verify_password
from ..models import DashboardUser, Tenant

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class MembershipOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: UUID
    tenant_name: str
    role: str


class UserOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    email: str
    tenant_ids: list[UUID]
    is_platform_admin: bool = False
    memberships: list[MembershipOut] = []


class LoginOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class ChangePasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


async def _user_out(session: AsyncSession, u: CurrentUser) -> UserOut:
    if not u.tenant_ids:
        return UserOut(user_id=u.user_id, email=u.email, tenant_ids=[], is_platform_admin=u.is_platform_admin)
    rows = await session.execute(select(Tenant.id, Tenant.name).where(Tenant.id.in_(u.tenant_ids)).order_by(Tenant.created_at))
    ms = [MembershipOut(tenant_id=tid, tenant_name=name, role="platform_admin" if u.is_platform_admin else u.roles[tid]) for tid, name in rows.all()]
    return UserOut(user_id=u.user_id, email=u.email, tenant_ids=sorted(u.tenant_ids, key=str), is_platform_admin=u.is_platform_admin, memberships=ms)


@router.post("/login", response_model=LoginOut)
async def login(body: LoginIn, request: Request, session: Annotated[AsyncSession, Depends(get_session)]) -> LoginOut:
    settings = request.app.state.settings
    if settings.dashboard_auth == "disabled":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Login is disabled (DASHBOARD_AUTH=disabled)")
    email = body.email.lower()
    key = f"{request.client.host if request.client else '?'}:{email}"
    throttle = request.app.state.login_throttle
    if throttle.is_locked(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts; try again later")
    user = (await session.execute(select(DashboardUser).where(DashboardUser.email == email))).scalar_one_or_none()
    ok = verify_password(body.password, user.password_hash if user else None)
    if not ok or user is None or not user.is_active:
        throttle.record_failure(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    throttle.clear(key)
    token, expires_in = create_access_token(user, settings.jwt_secret, settings.jwt_ttl_minutes)
    current = await load_current_user(session, user.id)
    assert current is not None
    return LoginOut(access_token=token, expires_in=expires_in, user=await _user_out(session, current))


@router.get("/me", response_model=UserOut)
async def me(user: Annotated[CurrentUser, Depends(require_user)], session: Annotated[AsyncSession, Depends(get_session)]) -> UserOut:
    return await _user_out(session, user)


@router.post("/change-password", status_code=204)
async def change_password(body: ChangePasswordIn, user: Annotated[CurrentUser, Depends(require_user)],
                          session: Annotated[AsyncSession, Depends(get_session)]) -> Response:
    row = await session.get(DashboardUser, user.user_id)
    if row is None or not verify_password(body.current_password, row.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Current password is incorrect")
    row.password_hash = hash_password(body.new_password)
    await session.commit()
    return Response(status_code=204)
