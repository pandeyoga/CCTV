import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { MembershipOut } from "../api/types";
import { AUTH_DISABLED, readSession, SESSION_CHANGED, writeSession, type Session } from "../lib/session";

interface AuthValue {
  session: Session | null;
  authDisabled: boolean;
  isPlatformAdmin: boolean;
  memberships: MembershipOut[];
  /** True when the user may manage at least one tenant (owner or platform admin). */
  canManageAny: boolean;
  canManage: (tenantId: string) => boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<Session | null>(() => readSession());

  useEffect(() => {
    const sync = () => setSession(readSession());
    window.addEventListener(SESSION_CHANGED, sync);
    window.addEventListener("storage", sync);
    return () => { window.removeEventListener(SESSION_CHANGED, sync); window.removeEventListener("storage", sync); };
  }, []);

  const refreshUser = useCallback(async () => {
    const s = readSession();
    if (!s) return;
    const user = await api.me();
    writeSession({ ...s, user });
  }, []);

  // Sessions written before roles existed lack `memberships`; refresh them once so the UI can show management.
  useEffect(() => {
    if (session && !Array.isArray(session.user.memberships)) void refreshUser().catch(() => undefined);
  }, [session, refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    const out = await api.login(email.trim().toLowerCase(), password);
    queryClient.clear();
    writeSession({ accessToken: out.access_token, expiresAt: Date.now() + out.expires_in * 1000, user: out.user });
  }, [queryClient]);

  const logout = useCallback(() => { writeSession(null); queryClient.clear(); }, [queryClient]);

  const value = useMemo<AuthValue>(() => {
    const memberships = session?.user.memberships ?? [];
    const isPlatformAdmin = AUTH_DISABLED || Boolean(session?.user.is_platform_admin);
    const canManage = (tenantId: string) => isPlatformAdmin || memberships.some((m) => m.tenant_id === tenantId && m.role === "owner");
    return {
      session, authDisabled: AUTH_DISABLED, isPlatformAdmin, memberships,
      canManageAny: isPlatformAdmin || memberships.some((m) => m.role === "owner"),
      canManage, login, logout, refreshUser,
    };
  }, [session, login, logout, refreshUser]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export function useAuth(): AuthValue {
  const v = useContext(AuthContext);
  if (!v) throw new Error("useAuth must be used inside AuthProvider");
  return v;
}
