/** Browser-side session for the dashboard JWT (ADR-018). No shared secret lives in the bundle. */
import type { UserOut } from "../api/types";

export interface Session {
  accessToken: string;
  expiresAt: number; // epoch ms
  user: UserOut;
}

const KEY = "pc.session.v1";
export const SESSION_CHANGED = "pc:session-changed";

/** Explicit local-dev mirror of the backend's DASHBOARD_AUTH=disabled; never a fallback for missing config. */
export const AUTH_DISABLED = process.env.REACT_APP_DASHBOARD_AUTH === "disabled";

export function readSession(): Session | null {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as Session;
    if (!s.accessToken || !s.user || s.expiresAt <= Date.now()) {
      window.localStorage.removeItem(KEY);
      return null;
    }
    return s;
  } catch {
    return null;
  }
}

export function writeSession(s: Session | null): void {
  if (s) window.localStorage.setItem(KEY, JSON.stringify(s));
  else window.localStorage.removeItem(KEY);
  window.dispatchEvent(new Event(SESSION_CHANGED));
}

export function getAccessToken(): string | null {
  return readSession()?.accessToken ?? null;
}
