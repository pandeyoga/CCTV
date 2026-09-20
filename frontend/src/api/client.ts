import type {
  AlertListOut, AlertOut, AlertRulesOut, CameraOut, ChannelsOut, DeviceKeyOut, DeviceOut, DeviceWithStoreOut, EnterSide, HeartbeatHistoryOut, HourlyOut, LineOut, LoginOut, MemberOut, Point, RangeReportOut, StoreOut,
  StoreOverviewOut, SummaryOut, TelegramTestOut, TenantOut, UserAdminOut, UserOut, ZoneOccupancyOut, ZoneOut,
} from "./types";
import { AUTH_DISABLED, getAccessToken, writeSession } from "../lib/session";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const MESSAGES: Record<number, string> = {
  401: "Sesi berakhir atau tidak valid; silakan masuk lagi",
  403: "Anda tidak memiliki izin untuk tindakan ini",
  404: "Data tidak ditemukan atau Anda tidak memiliki akses",
  409: "Data bentrok dengan yang sudah ada",
  422: "Data yang dikirim tidak valid",
  429: "Terlalu banyak percobaan; coba lagi beberapa menit",
};

/** FastAPI returns `detail` as a string or (422) a list of {msg}. Never render the raw object. */
function detailOf(body: unknown): string | null {
  const d = (body as { detail?: unknown } | null)?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((e) => (e && typeof e.msg === "string" ? e.msg : "")).filter(Boolean).join("; ") || null;
  return null;
}

async function request<T>(path: string, init: RequestInit = {}, withAuth = true): Promise<T> {
  if (!BACKEND_URL) throw new ApiError(0, "REACT_APP_BACKEND_URL tidak dikonfigurasi");
  const headers: Record<string, string> = { Accept: "application/json", ...(init.headers as Record<string, string>) };
  if (withAuth && !AUTH_DISABLED) {
    const token = getAccessToken();
    if (!token) throw new ApiError(401, MESSAGES[401]);
    headers.Authorization = `Bearer ${token}`;
  }
  let res: Response;
  try {
    res = await fetch(`${BACKEND_URL}/api${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Tidak dapat terhubung ke server API");
  }
  if (res.status === 401 && withAuth) writeSession(null); // token expired / user deactivated -> back to login
  if (!res.ok) {
    let detail: string | null = null;
    try { detail = detailOf(await res.json()); } catch { /* non-JSON body */ }
    const base = MESSAGES[res.status] ?? `API mengembalikan HTTP ${res.status}`;
    throw new ApiError(res.status, detail && res.status !== 401 ? `${base}: ${detail}` : base);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const get = <T,>(path: string) => request<T>(path);
const send = <T,>(method: "POST" | "PATCH" | "PUT" | "DELETE", path: string, body?: unknown) =>
  request<T>(path, { method, headers: body === undefined ? {} : { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  stores: () => get<StoreOut[]>("/v1/stores"),
  summary: (storeId: string, date: string) => get<SummaryOut>(`/v1/stores/${storeId}/summary?date=${date}`),
  hourly: (storeId: string, date: string) => get<HourlyOut>(`/v1/stores/${storeId}/hourly?date=${date}`),
  devices: (storeId: string) => get<DeviceOut[]>(`/v1/stores/${storeId}/devices`),
  allDevices: () => get<DeviceWithStoreOut[]>("/v1/devices"),
  report: (storeId: string, from: string, to: string) => get<RangeReportOut>(`/v1/stores/${storeId}/report?from=${from}&to=${to}`),
  overview: () => get<StoreOverviewOut[]>("/v1/overview"),
  heartbeatHistory: (deviceId: string, hours = 24) => get<HeartbeatHistoryOut>(`/v1/devices/${deviceId}/heartbeats?hours=${hours}`),
  // alerts (ADR-028)
  alerts: (status: "open" | "resolved" | "all", storeId?: string) => get<AlertListOut>(`/v1/alerts?status=${status}${storeId ? `&store_id=${storeId}` : ""}`),
  ackAlert: (id: string) => send<AlertOut>("POST", `/v1/alerts/${id}/ack`),
  alertRules: (storeId: string) => get<AlertRulesOut>(`/v1/stores/${storeId}/alert-rules`),
  putAlertRules: (storeId: string, body: { heartbeat_lost_min: number; camera_down_min: number; buffer_pending_threshold: number; no_events_min: number | null }) =>
    send<AlertRulesOut>("PUT", `/v1/stores/${storeId}/alert-rules`, body),
  resetAlertRules: (storeId: string) => send<AlertRulesOut>("DELETE", `/v1/stores/${storeId}/alert-rules`),
  // telegram channel (ADR-029)
  channels: () => get<ChannelsOut>("/v1/notifications/channels"),
  putTelegram: (storeId: string, chat_id: string | null) => send<StoreOut>("PUT", `/v1/stores/${storeId}/telegram`, { chat_id }),
  testTelegram: (storeId: string) => send<TelegramTestOut>("POST", `/v1/stores/${storeId}/telegram/test`),
  // camera geometry (ADR-030) + zones (ADR-031)
  lines: (cameraId: string) => get<LineOut[]>(`/v1/cameras/${cameraId}/lines`),
  putLine: (cameraId: string, lineId: string, body: { ax: number; ay: number; bx: number; by: number; enter_side: EnterSide }) =>
    send<LineOut>("PUT", `/v1/cameras/${cameraId}/lines/${encodeURIComponent(lineId)}`, body),
  deleteLine: (cameraId: string, lineId: string) => send<void>("DELETE", `/v1/cameras/${cameraId}/lines/${encodeURIComponent(lineId)}`),
  snapshotBlob: async (cameraId: string): Promise<Blob | null> => {
    const token = getAccessToken();
    const res = await fetch(`${BACKEND_URL}/api/v1/cameras/${cameraId}/snapshot`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (res.status === 404) return null;
    if (!res.ok) throw new ApiError(res.status, MESSAGES[res.status] ?? `API mengembalikan HTTP ${res.status}`);
    return res.blob();
  },
  storeZones: (storeId: string) => get<ZoneOut[]>(`/v1/stores/${storeId}/zones`),
  cameraZones: (cameraId: string) => get<ZoneOut[]>(`/v1/cameras/${cameraId}/zones`),
  createZone: (cameraId: string, body: { external_id: string; name: string; polygon: Point[] }) => send<ZoneOut>("POST", `/v1/cameras/${cameraId}/zones`, body),
  patchZone: (zoneId: string, body: { name?: string; polygon?: Point[] }) => send<ZoneOut>("PATCH", `/v1/zones/${zoneId}`, body),
  deleteZone: (zoneId: string) => send<void>("DELETE", `/v1/zones/${zoneId}`),
  zoneOccupancy: (storeId: string, date: string) => get<ZoneOccupancyOut>(`/v1/stores/${storeId}/zones/occupancy?date=${date}`),
  me: () => get<UserOut>("/auth/me"),
  login: (email: string, password: string) =>
    request<LoginOut>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }, false),
  changePassword: (current_password: string, new_password: string) => send<void>("POST", "/auth/change-password", { current_password, new_password }),

  // management (ADR-024)
  tenants: () => get<TenantOut[]>("/v1/tenants"),
  createTenant: (body: { name: string; contact_email?: string | null }) => send<TenantOut>("POST", "/v1/tenants", body),
  patchTenant: (id: string, body: { name?: string; contact_email?: string | null }) => send<TenantOut>("PATCH", `/v1/tenants/${id}`, body),
  createStore: (body: { tenant_id: string; name: string; timezone: string; open_time?: string | null; close_time?: string | null }) => send<StoreOut>("POST", "/v1/stores", body),
  patchStore: (id: string, body: { name?: string; timezone?: string; open_time?: string | null; close_time?: string | null }) => send<StoreOut>("PATCH", `/v1/stores/${id}`, body),
  createDevice: (storeId: string, name: string) => send<DeviceKeyOut>("POST", `/v1/stores/${storeId}/devices`, { name }),
  patchDevice: (id: string, body: { name?: string; is_active?: boolean }) => send<DeviceOut>("PATCH", `/v1/devices/${id}`, body),
  rotateDeviceKey: (id: string) => send<DeviceKeyOut>("POST", `/v1/devices/${id}/rotate-key`),
  cameras: (storeId: string) => get<CameraOut[]>(`/v1/stores/${storeId}/cameras`),
  createCamera: (storeId: string, body: { external_id: string; name: string; device_id?: string | null }) => send<CameraOut>("POST", `/v1/stores/${storeId}/cameras`, body),
  patchCamera: (id: string, body: { name?: string; device_id?: string | null; clear_device?: boolean }) => send<CameraOut>("PATCH", `/v1/cameras/${id}`, body),
  deleteCamera: (id: string) => send<void>("DELETE", `/v1/cameras/${id}`),
  members: (tenantId: string) => get<MemberOut[]>(`/v1/tenants/${tenantId}/members`),
  addMember: (tenantId: string, body: { email: string; role: "owner" | "staff"; password?: string }) => send<MemberOut>("POST", `/v1/tenants/${tenantId}/members`, body),
  patchMember: (tenantId: string, userId: string, role: "owner" | "staff") => send<MemberOut>("PATCH", `/v1/tenants/${tenantId}/members/${userId}`, { role }),
  removeMember: (tenantId: string, userId: string) => send<void>("DELETE", `/v1/tenants/${tenantId}/members/${userId}`),
  resetPassword: (userId: string, password: string) => send<void>("POST", `/v1/users/${userId}/reset-password`, { password }),
  users: () => get<UserAdminOut[]>("/v1/users"),
  patchUser: (userId: string, is_active: boolean) => send<UserAdminOut>("PATCH", `/v1/users/${userId}`, { is_active }),
};
