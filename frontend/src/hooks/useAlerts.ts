import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { REFRESH_MS } from "./useDashboardData";

export type AlertStatusFilter = "open" | "resolved" | "all";

export const useAlerts = (status: AlertStatusFilter, storeId?: string) =>
  useQuery({ queryKey: ["alerts", status, storeId ?? null], queryFn: () => api.alerts(status, storeId), refetchInterval: REFRESH_MS });

/** Bell badge: open + unacknowledged count, polled on every page. */
export const useAlertBadge = (enabled: boolean) =>
  useQuery({ queryKey: ["alerts", "open", null], queryFn: () => api.alerts("open"), refetchInterval: REFRESH_MS, enabled });

export const useAlertRules = (storeId: string, enabled = true) =>
  useQuery({ queryKey: ["alert-rules", storeId], queryFn: () => api.alertRules(storeId), enabled });
