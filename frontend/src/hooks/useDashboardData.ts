import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export const REFRESH_MS = 30_000;

export function useStores() {
  return useQuery({ queryKey: ["stores"], queryFn: api.stores, refetchInterval: REFRESH_MS });
}

export function useAllDevices() {
  return useQuery({ queryKey: ["devices", "all"], queryFn: api.allDevices, refetchInterval: REFRESH_MS });
}

export function useOverview() {
  return useQuery({ queryKey: ["overview"], queryFn: api.overview, refetchInterval: REFRESH_MS });
}

export function useRangeReport(storeId: string | undefined, from: string, to: string) {
  return useQuery({ queryKey: ["report", storeId, from, to], queryFn: () => api.report(storeId!, from, to), enabled: Boolean(storeId) && from <= to });
}

export function useStoreDay(storeId: string | undefined, date: string) {
  const enabled = Boolean(storeId);
  const summary = useQuery({
    queryKey: ["summary", storeId, date],
    queryFn: () => api.summary(storeId!, date),
    enabled, refetchInterval: REFRESH_MS,
  });
  const hourly = useQuery({
    queryKey: ["hourly", storeId, date],
    queryFn: () => api.hourly(storeId!, date),
    enabled, refetchInterval: REFRESH_MS,
  });
  const devices = useQuery({
    queryKey: ["devices", storeId],
    queryFn: () => api.devices(storeId!),
    enabled, refetchInterval: REFRESH_MS,
  });
  const updatedAt = Math.max(summary.dataUpdatedAt, hourly.dataUpdatedAt, devices.dataUpdatedAt) || null;
  const refetchAll = () => Promise.all([summary.refetch(), hourly.refetch(), devices.refetch()]);
  return { summary, hourly, devices, updatedAt, refetchAll, isFetching: summary.isFetching || hourly.isFetching || devices.isFetching };
}
