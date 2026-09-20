import { AlertOctagon, CameraOff, Clock, Database, EyeOff } from "lucide-react";
import type { AlertRuleName, AlertSeverity } from "../api/types";

export const ALERT_RULE: Record<AlertRuleName, { label: string; Icon: typeof Clock; hint: string }> = {
  heartbeat_lost: { label: "Tanpa heartbeat", Icon: Clock, hint: "Edge agent berhenti melapor; cek daya, jaringan, atau proses agent." },
  camera_down: { label: "Kamera terputus", Icon: CameraOff, hint: "Agent hidup tetapi tidak mendapat gambar dari kamera (RTSP/kabel)." },
  buffer_full: { label: "Buffer penuh", Icon: Database, hint: "Event menumpuk di edge karena tidak terkirim ke server." },
  no_events_open_hours: { label: "Tidak ada event pada jam buka", Icon: EyeOff, hint: "Perangkat terhubung tetapi tidak ada orang terhitung; cek posisi garis atau kamera." },
};

export const ALERT_SEVERITY: Record<AlertSeverity, { label: string; cls: string; bar: string; Icon: typeof Clock }> = {
  critical: { label: "Kritis", cls: "bg-danger-soft text-danger border-red-200", bar: "border-l-danger", Icon: AlertOctagon },
  warning: { label: "Peringatan", cls: "bg-warn-soft text-warn border-amber-200", bar: "border-l-warn", Icon: AlertOctagon },
};

export const durationLabel = (fromIso: string, toIso: string | null, now: Date): string => {
  const s = Math.max(0, Math.floor(((toIso ? Date.parse(toIso) : now.getTime()) - Date.parse(fromIso)) / 1000));
  if (s < 60) return `${s} dtk`;
  if (s < 3600) return `${Math.floor(s / 60)} mnt`;
  if (s < 86400) return `${Math.floor(s / 3600)} j ${Math.floor((s % 3600) / 60)} mnt`;
  return `${Math.floor(s / 86400)} hari ${Math.floor((s % 86400) / 3600)} j`;
};
