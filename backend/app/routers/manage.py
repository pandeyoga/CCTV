"""Self-service management (ADR-024): tenants, stores, devices, cameras, members. Every write is scoped by the
caller's role: platform admin (all tenants) or tenant `owner`; `staff` is read-only. Nothing in a request body
grants access — tenant/store ownership is always resolved from the DB row and checked against the caller."""
from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import CurrentUser, forbidden, get_session, hash_password, issue_device_key, require_platform_admin, require_user
from ..hours import parse_hhmm
from ..models import Camera, CountEvent, DashboardUser, Device, Store, Tenant, TenantMembership
from ..schemas import CameraOut, DeviceKeyOut, DeviceOut, MemberOut, MembershipOut, StoreOut, TenantOut, UserAdminOut
from .devices import device_fields

router = APIRouter(prefix="/api/v1", tags=["manage"])

User = Annotated[CurrentUser, Depends(require_user)]
Admin = Annotated[CurrentUser, Depends(require_platform_admin)]
Db = Annotated[AsyncSession, Depends(get_session)]
Role = Literal["owner", "staff"]
NAME = Field(min_length=1, max_length=128)


def _tz(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("unknown IANA timezone")
    return value


# ----------------------------------------------------------------------------- bodies
class TenantIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = NAME
    contact_email: EmailStr | None = None


class TenantPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=128)
    contact_email: EmailStr | None = None


class StoreIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: UUID
    name: str = NAME
    timezone: str
    open_time: str | None = None
    close_time: str | None = None

    _tz = field_validator("timezone")(lambda cls, v: _tz(v))
    _hours = model_validator(mode="after")(lambda self: _check_hours(self))


class StorePatch(BaseModel):
    """`open_time`/`close_time` must be sent together (both set or both null); omitting them leaves hours unchanged."""

    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=128)
    timezone: str | None = None
    open_time: str | None = None
    close_time: str | None = None

    _tz = field_validator("timezone")(lambda cls, v: _tz(v) if v is not None else v)
    _hours = model_validator(mode="after")(lambda self: _check_hours(self))

    @property
    def hours_set(self) -> bool:
        return "open_time" in self.model_fields_set or "close_time" in self.model_fields_set


def _check_hours(body):
    if (body.open_time is None) != (body.close_time is None):
        raise ValueError("open_time and close_time must be set together (or both null for 24 h)")
    if body.open_time is not None:
        if parse_hhmm(body.open_time) == parse_hhmm(body.close_time):
            raise ValueError("open_time and close_time must differ (leave both empty for 24 h)")
    return body


class DeviceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = NAME


class DevicePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=128)
    is_active: bool | None = None


class CameraIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = NAME
    device_id: UUID | None = None


class CameraPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=128)
    device_id: UUID | None = None
    clear_device: bool = False


class MemberIn(BaseModel):
    """Existing user (by email) gets a membership; unknown email creates the user and requires a password."""

    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    role: Role
    password: str | None = Field(default=None, min_length=10, max_length=256)


class MemberPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role


class PasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=10, max_length=256)


class UserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool


# ----------------------------------------------------------------------------- helpers
def _role_for(user: CurrentUser, tenant_id: UUID) -> str:
    return "platform_admin" if user.is_platform_admin else user.roles[tenant_id]


async def _tenant_out(s: AsyncSession, t: Tenant, user: CurrentUser) -> TenantOut:
    n = (await s.execute(select(func.count()).select_from(Store).where(Store.tenant_id == t.id))).scalar_one()
    return TenantOut(tenant_id=t.id, name=t.name, contact_email=t.contact_email, role=_role_for(user, t.id),
                     store_count=n, created_at=t.created_at)


async def _visible_tenant(s: AsyncSession, tenant_id: UUID, user: CurrentUser) -> Tenant:
    t = await s.get(Tenant, tenant_id)
    if t is None or tenant_id not in user.tenant_ids:
        raise HTTPException(404, "tenant not found")
    return t


async def _managed_tenant(s: AsyncSession, tenant_id: UUID, user: CurrentUser) -> Tenant:
    t = await _visible_tenant(s, tenant_id, user)
    if not user.can_manage(t.id):
        raise forbidden("Owner role required for this tenant")
    return t


async def _managed_store(s: AsyncSession, store_id: UUID, user: CurrentUser) -> Store:
    st = await s.get(Store, store_id)
    if st is None or st.tenant_id not in user.tenant_ids:
        raise HTTPException(404, "store not found")
    if not user.can_manage(st.tenant_id):
        raise forbidden("Owner role required for this store")
    return st


async def _visible_store(s: AsyncSession, store_id: UUID, user: CurrentUser) -> Store:
    st = await s.get(Store, store_id)
    if st is None or st.tenant_id not in user.tenant_ids:
        raise HTTPException(404, "store not found")
    return st


async def _managed_device(s: AsyncSession, device_id: UUID, user: CurrentUser) -> Device:
    d = await s.get(Device, device_id)
    if d is None or d.tenant_id not in user.tenant_ids:
        raise HTTPException(404, "device not found")
    if not user.can_manage(d.tenant_id):
        raise forbidden("Owner role required for this device")
    return d


async def _managed_camera(s: AsyncSession, camera_id: UUID, user: CurrentUser) -> Camera:
    c = await s.get(Camera, camera_id)
    if c is None or c.tenant_id not in user.tenant_ids:
        raise HTTPException(404, "camera not found")
    if not user.can_manage(c.tenant_id):
        raise forbidden("Owner role required for this camera")
    return c


async def _device_in_store(s: AsyncSession, device_id: UUID, store: Store) -> Device:
    d = await s.get(Device, device_id)
    if d is None or d.store_id != store.id:
        raise HTTPException(422, "device_id must belong to the same store")
    return d


def _camera_out(c: Camera) -> CameraOut:
    return CameraOut(camera_id=c.id, store_id=c.store_id, device_id=c.device_id, external_id=c.external_id, name=c.name, created_at=c.created_at)


def _store_out(st: Store) -> StoreOut:
    return StoreOut(store_id=st.id, tenant_id=st.tenant_id, name=st.name, timezone=st.timezone, open_time=st.open_time, close_time=st.close_time)


async def _name_free(s: AsyncSession, model, where, msg: str) -> None:
    if (await s.execute(select(model.id).where(*where))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, msg)


# ----------------------------------------------------------------------------- tenants
@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants(s: Db, user: User) -> list[TenantOut]:
    if not user.tenant_ids:
        return []
    rows = (await s.execute(select(Tenant).where(Tenant.id.in_(user.tenant_ids)).order_by(Tenant.created_at))).scalars()
    return [await _tenant_out(s, t, user) for t in rows]


@router.post("/tenants", response_model=TenantOut, status_code=201)
async def create_tenant(body: TenantIn, s: Db, user: Admin) -> TenantOut:
    await _name_free(s, Tenant, [Tenant.name == body.name], "tenant name already exists")
    t = Tenant(name=body.name, contact_email=body.contact_email)
    s.add(t)
    await s.commit()
    return await _tenant_out(s, t, user)


@router.patch("/tenants/{tenant_id}", response_model=TenantOut)
async def patch_tenant(tenant_id: UUID, body: TenantPatch, s: Db, user: Admin) -> TenantOut:
    t = await _visible_tenant(s, tenant_id, user)
    if body.name is not None and body.name != t.name:
        await _name_free(s, Tenant, [Tenant.name == body.name], "tenant name already exists")
        t.name = body.name
    if "contact_email" in body.model_fields_set:
        t.contact_email = body.contact_email
    await s.commit()
    return await _tenant_out(s, t, user)


# ----------------------------------------------------------------------------- stores
@router.post("/stores", response_model=StoreOut, status_code=201)
async def create_store(body: StoreIn, s: Db, user: User) -> StoreOut:
    t = await _managed_tenant(s, body.tenant_id, user)
    await _name_free(s, Store, [Store.tenant_id == t.id, Store.name == body.name], "store name already exists in this tenant")
    st = Store(tenant_id=t.id, name=body.name, timezone=body.timezone, open_time=body.open_time, close_time=body.close_time)
    s.add(st)
    await s.commit()
    return _store_out(st)


@router.patch("/stores/{store_id}", response_model=StoreOut)
async def patch_store(store_id: UUID, body: StorePatch, s: Db, user: User) -> StoreOut:
    st = await _managed_store(s, store_id, user)
    if body.name is not None and body.name != st.name:
        await _name_free(s, Store, [Store.tenant_id == st.tenant_id, Store.name == body.name], "store name already exists in this tenant")
        st.name = body.name
    if body.timezone is not None:
        st.timezone = body.timezone
    if body.hours_set:
        st.open_time, st.close_time = body.open_time, body.close_time
    await s.commit()
    return _store_out(st)


# ----------------------------------------------------------------------------- devices
@router.post("/stores/{store_id}/devices", response_model=DeviceKeyOut, status_code=201)
async def create_device(store_id: UUID, body: DeviceIn, s: Db, user: User) -> DeviceKeyOut:
    st = await _managed_store(s, store_id, user)
    await _name_free(s, Device, [Device.store_id == st.id, Device.name == body.name], "device name already exists in this store")
    key = issue_device_key()
    d = Device(tenant_id=st.tenant_id, store_id=st.id, name=body.name, key_id=key.key_id, secret_hash=key.secret_hash, api_key_prefix=key.prefix)
    s.add(d)
    await s.commit()
    await s.refresh(d)
    return DeviceKeyOut(device=DeviceOut(**device_fields(d)), api_key_show_once=key.token)


@router.patch("/devices/{device_id}", response_model=DeviceOut)
async def patch_device(device_id: UUID, body: DevicePatch, s: Db, user: User) -> DeviceOut:
    d = await _managed_device(s, device_id, user)
    if body.name is not None and body.name != d.name:
        await _name_free(s, Device, [Device.store_id == d.store_id, Device.name == body.name], "device name already exists in this store")
        d.name = body.name
    if body.is_active is not None:
        d.is_active = body.is_active
    await s.commit()
    return DeviceOut(**device_fields(d))


@router.post("/devices/{device_id}/rotate-key", response_model=DeviceKeyOut)
async def rotate_device_key(device_id: UUID, s: Db, user: User) -> DeviceKeyOut:
    """The previous key stops working immediately; the edge agent must be updated with the new EDGE_API_KEY."""
    d = await _managed_device(s, device_id, user)
    key = issue_device_key()
    d.key_id, d.secret_hash, d.api_key_prefix = key.key_id, key.secret_hash, key.prefix
    await s.commit()
    return DeviceKeyOut(device=DeviceOut(**device_fields(d)), api_key_show_once=key.token)


# ----------------------------------------------------------------------------- cameras
@router.get("/stores/{store_id}/cameras", response_model=list[CameraOut])
async def list_cameras(store_id: UUID, s: Db, user: User) -> list[CameraOut]:
    st = await _visible_store(s, store_id, user)
    rows = (await s.execute(select(Camera).where(Camera.store_id == st.id).order_by(Camera.created_at))).scalars()
    return [_camera_out(c) for c in rows]


@router.post("/stores/{store_id}/cameras", response_model=CameraOut, status_code=201)
async def create_camera(store_id: UUID, body: CameraIn, s: Db, user: User) -> CameraOut:
    st = await _managed_store(s, store_id, user)
    await _name_free(s, Camera, [Camera.store_id == st.id, Camera.external_id == body.external_id], "camera_id already exists in this store")
    if body.device_id is not None:
        await _device_in_store(s, body.device_id, st)
    c = Camera(tenant_id=st.tenant_id, store_id=st.id, device_id=body.device_id, external_id=body.external_id, name=body.name)
    s.add(c)
    await s.commit()
    return _camera_out(c)


@router.patch("/cameras/{camera_id}", response_model=CameraOut)
async def patch_camera(camera_id: UUID, body: CameraPatch, s: Db, user: User) -> CameraOut:
    c = await _managed_camera(s, camera_id, user)
    if body.name is not None:
        c.name = body.name
    if body.clear_device:
        c.device_id = None
    elif body.device_id is not None:
        st = await s.get(Store, c.store_id)
        await _device_in_store(s, body.device_id, st)
        c.device_id = body.device_id
    await s.commit()
    return _camera_out(c)


@router.delete("/cameras/{camera_id}", status_code=204)
async def delete_camera(camera_id: UUID, s: Db, user: User) -> Response:
    c = await _managed_camera(s, camera_id, user)
    n = (await s.execute(select(func.count()).select_from(CountEvent).where(CountEvent.camera_id == c.id))).scalar_one()
    if n:
        raise HTTPException(status.HTTP_409_CONFLICT, f"camera has {n} count events; unassign its device instead of deleting")
    await s.delete(c)
    await s.commit()
    return Response(status_code=204)


# ----------------------------------------------------------------------------- members
def _member_out(u: DashboardUser, role: str) -> MemberOut:
    return MemberOut(user_id=u.id, email=u.email, role=role, is_active=u.is_active, is_platform_admin=u.is_platform_admin, created_at=u.created_at)


async def _membership(s: AsyncSession, tenant_id: UUID, user_id: UUID) -> TenantMembership | None:
    return (await s.execute(select(TenantMembership).where(TenantMembership.tenant_id == tenant_id,
                                                           TenantMembership.user_id == user_id))).scalar_one_or_none()


@router.get("/tenants/{tenant_id}/members", response_model=list[MemberOut])
async def list_members(tenant_id: UUID, s: Db, user: User) -> list[MemberOut]:
    t = await _managed_tenant(s, tenant_id, user)
    rows = await s.execute(select(DashboardUser, TenantMembership.role).join(TenantMembership, TenantMembership.user_id == DashboardUser.id)
                           .where(TenantMembership.tenant_id == t.id).order_by(DashboardUser.created_at))
    return [_member_out(u, role) for u, role in rows.all()]


@router.post("/tenants/{tenant_id}/members", response_model=MemberOut, status_code=201)
async def add_member(tenant_id: UUID, body: MemberIn, s: Db, user: User) -> MemberOut:
    t = await _managed_tenant(s, tenant_id, user)
    email = body.email.lower()
    u = (await s.execute(select(DashboardUser).where(DashboardUser.email == email))).scalar_one_or_none()
    if u is None:
        if body.password is None:
            raise HTTPException(422, "password is required when creating a new user")
        u = DashboardUser(email=email, password_hash=hash_password(body.password))
        s.add(u)
        await s.flush()
    elif u.is_platform_admin:
        raise HTTPException(status.HTTP_409_CONFLICT, "platform admins already have access to every tenant")
    elif await _membership(s, t.id, u.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "user is already a member of this tenant")
    s.add(TenantMembership(user_id=u.id, tenant_id=t.id, role=body.role))
    await s.commit()
    return _member_out(u, body.role)


@router.patch("/tenants/{tenant_id}/members/{user_id}", response_model=MemberOut)
async def patch_member(tenant_id: UUID, user_id: UUID, body: MemberPatch, s: Db, user: User) -> MemberOut:
    t = await _managed_tenant(s, tenant_id, user)
    m = await _membership(s, t.id, user_id)
    if m is None:
        raise HTTPException(404, "member not found")
    if user_id == user.user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "you cannot change your own role")
    m.role = body.role
    await s.commit()
    return _member_out(await s.get(DashboardUser, user_id), m.role)


@router.delete("/tenants/{tenant_id}/members/{user_id}", status_code=204)
async def remove_member(tenant_id: UUID, user_id: UUID, s: Db, user: User) -> Response:
    t = await _managed_tenant(s, tenant_id, user)
    m = await _membership(s, t.id, user_id)
    if m is None:
        raise HTTPException(404, "member not found")
    if user_id == user.user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "you cannot remove your own access")
    await s.delete(m)
    await s.commit()
    return Response(status_code=204)


async def _manageable_user(s: AsyncSession, user_id: UUID, user: CurrentUser) -> DashboardUser:
    """Platform admin: any user. Owner: users who are members of a tenant the owner manages and are not platform admins."""
    target = await s.get(DashboardUser, user_id)
    if target is None:
        raise HTTPException(404, "user not found")
    if user.is_platform_admin:
        return target
    if target.is_platform_admin:
        raise HTTPException(404, "user not found")
    shared = (await s.execute(select(TenantMembership.tenant_id).where(TenantMembership.user_id == target.id))).scalars()
    if not any(user.can_manage(tid) for tid in shared):
        raise HTTPException(404, "user not found")
    return target


@router.post("/users/{user_id}/reset-password", status_code=204)
async def reset_password(user_id: UUID, body: PasswordIn, s: Db, user: User) -> Response:
    target = await _manageable_user(s, user_id, user)
    target.password_hash = hash_password(body.password)
    await s.commit()
    return Response(status_code=204)


@router.patch("/users/{user_id}", response_model=UserAdminOut)
async def patch_user(user_id: UUID, body: UserPatch, s: Db, user: Admin) -> UserAdminOut:
    target = await s.get(DashboardUser, user_id)
    if target is None:
        raise HTTPException(404, "user not found")
    if target.id == user.user_id and not body.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "you cannot deactivate yourself")
    target.is_active = body.is_active
    await s.commit()
    return (await _users_out(s, [target]))[0]


async def _users_out(s: AsyncSession, users: list[DashboardUser]) -> list[UserAdminOut]:
    rows = await s.execute(select(TenantMembership.user_id, TenantMembership.role, Tenant.id, Tenant.name)
                           .join(Tenant, Tenant.id == TenantMembership.tenant_id))
    by_user: dict[UUID, list[MembershipOut]] = {}
    for uid, role, tid, tname in rows.all():
        by_user.setdefault(uid, []).append(MembershipOut(tenant_id=tid, tenant_name=tname, role=role))
    return [UserAdminOut(user_id=u.id, email=u.email, is_active=u.is_active, is_platform_admin=u.is_platform_admin,
                         created_at=u.created_at, memberships=by_user.get(u.id, [])) for u in users]


@router.get("/users", response_model=list[UserAdminOut])
async def list_users(s: Db, user: Admin) -> list[UserAdminOut]:
    rows = (await s.execute(select(DashboardUser).order_by(DashboardUser.created_at))).scalars().all()
    return await _users_out(s, list(rows))
