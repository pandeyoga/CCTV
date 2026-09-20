import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { REFRESH_MS } from "./useDashboardData";

export const useLines = (cameraId: string, enabled = true) => useQuery({ queryKey: ["lines", cameraId], queryFn: () => api.lines(cameraId), enabled });
export const useCameraZones = (cameraId: string, enabled = true) => useQuery({ queryKey: ["zones", "camera", cameraId], queryFn: () => api.cameraZones(cameraId), enabled });
export const useStoreZones = (storeId: string | undefined) =>
  useQuery({ queryKey: ["zones", "store", storeId], queryFn: () => api.storeZones(storeId!), enabled: Boolean(storeId), refetchInterval: REFRESH_MS });
export const useZoneOccupancy = (storeId: string | undefined, date: string) =>
  useQuery({ queryKey: ["zones", "occupancy", storeId, date], queryFn: () => api.zoneOccupancy(storeId!, date), enabled: Boolean(storeId), refetchInterval: REFRESH_MS });
export const useChannels = () => useQuery({ queryKey: ["channels"], queryFn: api.channels, staleTime: 5 * 60_000 });

/** Snapshot JPEG as an object URL (auth header needed, so no plain <img src>). `null` = none uploaded yet. */
export function useSnapshotUrl(cameraId: string, snapshotAt: string | null) {
  const [state, setState] = useState<{ url: string | null; status: "loading" | "ready" | "none" | "error" }>({ url: null, status: "loading" });
  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    setState({ url: null, status: "loading" });
    api.snapshotBlob(cameraId)
      .then((blob) => {
        if (cancelled) return;
        if (!blob) return setState({ url: null, status: "none" });
        url = URL.createObjectURL(blob);
        setState({ url, status: "ready" });
      })
      .catch(() => !cancelled && setState({ url: null, status: "error" }));
    return () => { cancelled = true; if (url) URL.revokeObjectURL(url); };
  }, [cameraId, snapshotAt]);
  return state;
}
