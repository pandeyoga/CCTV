/** Dashboard read models. Mirror of docs/CONTRACTS.md ("Dashboard → Backend"). Do not add fields here that the API does not return. */

export interface StoreOut {
  store_id: string;
  tenant_id: string;
  name: string;
  timezone: string;
  open_time: string | null; // "HH:MM" store-local; both null => open 24 h (ADR-026)
  close_time: string | null;
}

export interface SummaryOut {
  store_id: string;
  date: string; // YYYY-MM-DD in store timezone
  timezone: string;
  enter: number;
  exit: number;
  occupancy_estimate: number;
  last_event_at: string | null; // UTC ISO
}

export interface HourBucket {
  hour_start: string; // store-local ISO with offset
  enter: number;
  exit: number;
}

export interface HourlyOut {
  store_id: string;
  date: string;
  timezone: string;
  buckets: HourBucket[];
}

export type SourceStatus = "ok" | "source_down";

export interface DeviceOut {
  device_id: string;
  name: string;
  is_active: boolean;
  last_event_at: string | null; // UTC ISO; server receive time of the last accepted event batch (visitor activity, not health)
  last_heartbeat_at: string | null; // UTC ISO; server receive time of the last heartbeat; null => status unknown
  source_status: SourceStatus | null;
  last_frame_age_s: number | null;
  pending_events: number | null;
  agent_version: string | null;
}

export interface DeviceWithStoreOut extends DeviceOut {
  store_id: string;
  store_name: string;
  store_timezone: string;
}

export type TenantRole = "platform_admin" | "owner" | "staff";

export interface MembershipOut {
  tenant_id: string;
  tenant_name: string;
  role: TenantRole;
}

export interface UserOut {
  user_id: string;
  email: string;
  tenant_ids: string[];
  is_platform_admin: boolean;
  memberships: MembershipOut[];
}

export interface LoginOut {
  access_token: string;
  token_type: "bearer";
  expires_in: number; // seconds
  user: UserOut;
}

// ---------------------------------------------------------------- management (ADR-024)
export interface TenantOut {
  tenant_id: string;
  name: string;
  contact_email: string | null;
  role: TenantRole; // the caller's role for this tenant
  store_count: number;
  created_at: string;
}

export interface CameraOut {
  camera_id: string;
  store_id: string;
  device_id: string | null;
  external_id: string; // == payload camera_id configured on the edge
  name: string;
  created_at: string;
}

export interface DeviceKeyOut {
  device: DeviceOut;
  api_key_show_once: string;
}

export interface MemberOut {
  user_id: string;
  email: string;
  role: "owner" | "staff";
  is_active: boolean;
  is_platform_admin: boolean;
  created_at: string;
}

export interface UserAdminOut {
  user_id: string;
  email: string;
  is_active: boolean;
  is_platform_admin: boolean;
  created_at: string;
  memberships: MembershipOut[];
}

// ---------------------------------------------------------------- reports (ADR-025)
export interface DayBucket {
  date: string; // YYYY-MM-DD store-local
  enter: number;
  exit: number;
}

export interface RangeTotals {
  from_date: string;
  to_date: string;
  days: number;
  enter: number;
  exit: number;
}

export interface HourProfile {
  hour: number; // 0..23 store-local
  enter: number;
  exit: number;
}

export interface RangeReportOut {
  store_id: string;
  timezone: string;
  open_time: string | null;
  close_time: string | null;
  outside_hours_excluded: number; // events in range outside opening hours, not counted
  current: RangeTotals;
  previous: RangeTotals; // immediately preceding period of equal length
  daily: DayBucket[];
  hourly_profile: HourProfile[];
}

export interface StoreOverviewOut {
  store_id: string;
  tenant_id: string;
  name: string;
  timezone: string;
  date: string; // today in the store timezone
  enter: number;
  exit: number;
  yesterday_enter: number;
  avg_enter_7d: number;
  last_event_at: string | null;
  devices_total: number;
  devices_problem: number; // always 0 while the store is closed
  is_open_now: boolean;
  open_time: string | null;
  close_time: string | null;
}

// ---------------------------------------------------------------- heartbeat history (ADR-027)
export type HeartbeatState = "connected" | "camera_down" | "stale" | "unknown";

export interface HeartbeatSegment {
  start: string; // UTC ISO
  end: string; // UTC ISO, exclusive
  status: HeartbeatState;
}

export interface HeartbeatHistoryOut {
  device_id: string;
  from_ts: string;
  to_ts: string;
  stale_after_s: number;
  samples: number;
  uptime_pct: number;
  segments: HeartbeatSegment[];
}
