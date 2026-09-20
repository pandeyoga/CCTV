import { Activity, CameraOff, Clock, HelpCircle, PowerOff } from "lucide-react";
import type { DeviceOut } from "../api/types";
import { HEARTBEAT_STALE_SECONDS, isHeartbeatStale } from "./time";

/** Liveness is heartbeat-based (Finding 4, ADR-020). Visitor events never imply health. */
export type DeviceStatus = "connected" | "camera_down" | "stale" | "unknown" | "inactive";

const STALE_MIN = Math.round(HEARTBEAT_STALE_SECONDS / 60);

export const DEVICE_STATUS: Record<DeviceStatus, { label: string; short: string; cls: string; dot: string; Icon: typeof Clock; problem: boolean }> = {
  camera_down: { label: "Terhubung, kamera terputus", short: "Kamera terputus", cls: "bg-warn-soft text-warn border-amber-200", dot: "bg-warn", Icon: CameraOff, problem: true },
  stale: { label: `Tanpa heartbeat > ${STALE_MIN} mnt`, short: "Tanpa heartbeat", cls: "bg-danger-soft text-danger border-red-200", dot: "bg-danger", Icon: Clock, problem: true },
  unknown: { label: "Belum diketahui", short: "Belum diketahui", cls: "bg-surface-2 text-txt-2 border-line", dot: "bg-zinc-400", Icon: HelpCircle, problem: false },
  connected: { label: "Terhubung", short: "Terhubung", cls: "bg-emerald-soft text-emerald-brand border-emerald-200", dot: "bg-emerald-brand", Icon: Activity, problem: false },
  inactive: { label: "Nonaktif", short: "Nonaktif", cls: "bg-surface-2 text-txt-2 border-line", dot: "bg-zinc-300", Icon: PowerOff, problem: false },
};

/** Display order: problems first. */
export const DEVICE_STATUS_ORDER: DeviceStatus[] = ["camera_down", "stale", "unknown", "connected", "inactive"];

export const statusOf = (d: DeviceOut, now: Date): DeviceStatus => {
  if (!d.is_active) return "inactive";
  if (d.last_heartbeat_at === null) return "unknown";
  if (isHeartbeatStale(d.last_heartbeat_at, now)) return "stale";
  return d.source_status === "source_down" ? "camera_down" : "connected";
};
