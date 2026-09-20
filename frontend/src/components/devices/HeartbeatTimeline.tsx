import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { HeartbeatSegment, HeartbeatState } from "../../api/types";

const STYLE: Record<HeartbeatState, { label: string; cls: string }> = {
  connected: { label: "Terhubung", cls: "bg-emerald-brand" },
  camera_down: { label: "Kamera terputus", cls: "bg-warn" },
  stale: { label: "Tanpa heartbeat", cls: "bg-danger" },
  unknown: { label: "Belum ada data", cls: "bg-zinc-300" },
};

const fmtDur = (s: number) => (s >= 3600 ? `${Math.floor(s / 3600)} j ${Math.round((s % 3600) / 60)} mnt` : `${Math.round(s / 60)} mnt`);
/** HH:MM in the store timezone (no seconds; en-GB gives a colon separator regardless of id-ID's dots). */
const hhmm = (iso: string, tz: string) => new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(iso));

const Segment = ({ s, total, from, tz }: { s: HeartbeatSegment; total: number; from: number; tz: string }) => {
  const a = Date.parse(s.start), b = Date.parse(s.end);
  const left = ((a - from) / total) * 100, width = ((b - a) / total) * 100;
  const title = `${STYLE[s.status].label}: ${hhmm(s.start, tz)} – ${hhmm(s.end, tz)} (${fmtDur((b - a) / 1000)})`;
  return <span data-testid="heartbeat-segment" data-status={s.status} title={title} className={`absolute inset-y-0 ${STYLE[s.status].cls}`} style={{ left: `${left}%`, width: `${Math.max(width, 0.15)}%` }} />;
};

export const HeartbeatTimeline = ({ deviceId, tz }: { deviceId: string; tz: string }) => {
  const q = useQuery({ queryKey: ["heartbeats", deviceId], queryFn: () => api.heartbeatHistory(deviceId, 24), refetchInterval: 60_000 });
  if (q.isPending) return <div data-testid="heartbeat-timeline-loading" className="h-16 animate-pulse rounded-ctl bg-surface-2" aria-hidden="true" />;
  if (!q.data) return <p className="text-xs text-danger">{(q.error as Error).message}</p>;
  const h = q.data;
  const from = Date.parse(h.from_ts), total = Date.parse(h.to_ts) - from;
  const downtime = h.segments.filter((s) => s.status === "stale" || s.status === "camera_down").reduce((a, s) => a + (Date.parse(s.end) - Date.parse(s.start)) / 1000, 0);
  const ticks = [0, 6, 12, 18, 24].map((k) => new Date(from + (k / 24) * total).toISOString());
  return (
    <div data-testid="heartbeat-timeline" className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <p className="text-txt-2">Riwayat heartbeat 24 jam terakhir · <span data-testid="heartbeat-uptime" className="tnum font-semibold text-txt">{h.uptime_pct.toLocaleString("id-ID")}% terhubung</span>{downtime > 0 && <span className="text-txt-3"> · gangguan {fmtDur(downtime)}</span>}</p>
        <p className="text-txt-3 tnum">{h.samples} heartbeat diterima</p>
      </div>
      <div role="img" aria-label={`Timeline heartbeat, ${h.uptime_pct}% terhubung`} className="relative h-5 overflow-hidden rounded-md bg-surface-2 ring-1 ring-line">
        {h.segments.map((s) => <Segment key={s.start} s={s} total={total} from={from} tz={tz} />)}
      </div>
      <div className="flex justify-between text-[10px] text-txt-3 tnum">{ticks.map((t) => <span key={t}>{hhmm(t, tz)}</span>)}</div>
      <ul className="flex flex-wrap gap-3 text-[11px] text-txt-2" aria-label="Legenda">
        {(Object.keys(STYLE) as HeartbeatState[]).map((k) => <li key={k} className="flex items-center gap-1.5"><span aria-hidden="true" className={`h-2 w-3 rounded-sm ${STYLE[k].cls}`} />{STYLE[k].label}</li>)}
      </ul>
    </div>
  );
};
