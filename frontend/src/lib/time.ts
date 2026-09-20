/** Store-timezone date helpers. All inputs are UTC ISO strings or YYYY-MM-DD; display uses the store's IANA tz. */

export function todayInTz(tz: string, now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

export function addDays(ymd: string, days: number): string {
  const [y, m, d] = ymd.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d + days, 12));
  return t.toISOString().slice(0, 10);
}

export function formatDateLong(ymd: string, locale = "id-ID"): string {
  const [y, m, d] = ymd.split("-").map(Number);
  return new Intl.DateTimeFormat(locale, { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })
    .format(new Date(Date.UTC(y, m - 1, d, 12)));
}

export function formatTimeInTz(iso: string, tz: string, locale = "id-ID"): string {
  return new Intl.DateTimeFormat(locale, { timeZone: tz, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })
    .format(new Date(iso));
}

export function formatDateTimeInTz(iso: string, tz: string, locale = "id-ID"): string {
  return new Intl.DateTimeFormat(locale, {
    timeZone: tz, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(new Date(iso));
}

export function secondsSince(iso: string, now: Date = new Date()): number {
  return Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / 1000));
}

export function relativeTime(iso: string, now: Date = new Date()): string {
  const s = secondsSince(iso, now);
  if (s < 60) return `${s} dtk lalu`;
  if (s < 3600) return `${Math.floor(s / 60)} mnt lalu`;
  if (s < 86400) return `${Math.floor(s / 3600)} jam lalu`;
  return `${Math.floor(s / 86400)} hari lalu`;
}

export const STALE_AFTER_SECONDS = 5 * 60;

export function isStale(iso: string | null, now: Date = new Date()): boolean {
  return iso === null || secondsSince(iso, now) > STALE_AFTER_SECONDS;
}

/** Edge heartbeat interval (edge `backend.heartbeat_interval_s` default) and the stale threshold = 3 intervals. See docs/CONTRACTS.md. */
export const HEARTBEAT_INTERVAL_SECONDS = 60;
export const HEARTBEAT_STALE_SECONDS = 3 * HEARTBEAT_INTERVAL_SECONDS;

export function isHeartbeatStale(iso: string, now: Date = new Date()): boolean {
  return secondsSince(iso, now) > HEARTBEAT_STALE_SECONDS;
}

/** "2026-06-01T09:00:00+07:00" -> "09" */
export function hourLabel(hourStartIso: string): string {
  return hourStartIso.slice(11, 13);
}
