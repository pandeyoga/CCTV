import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, Store } from "lucide-react";
import type { DeviceWithStoreOut } from "../../api/types";
import { DEVICE_STATUS, type DeviceStatus } from "../../lib/deviceStatus";
import { formatDateTimeInTz, relativeTime } from "../../lib/time";
import { HeartbeatTimeline } from "./HeartbeatTimeline";

interface Props {
  d: DeviceWithStoreOut;
  st: DeviceStatus;
  now: Date;
}

const Cell = ({ label, children, testId }: { label: string; children: React.ReactNode; testId: string }) => (
  <div data-testid={testId} className="min-w-0">
    <p className="text-[11px] font-medium text-txt-3">{label}</p>
    <p className="truncate text-xs text-txt-2 tnum">{children}</p>
  </div>
);

export const DeviceRow = ({ d, st, now }: Props) => {
  const { Icon, label, cls, problem } = DEVICE_STATUS[st];
  const [open, setOpen] = useState(false);
  const tz = d.store_timezone;
  const when = (iso: string | null, none: string) => (iso ? `${relativeTime(iso, now)} · ${formatDateTimeInTz(iso, tz)}` : none);
  return (
    <li data-testid="devices-row" data-status={st} className={`fade-in transition-colors hover:bg-surface-2/60 ${problem ? "border-l-4 border-l-warn/70" : ""}`}>
      <div className="grid gap-3 p-4 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,2fr)_auto] sm:items-center">
        <div className="flex min-w-0 items-center gap-3">
          <span aria-hidden="true" className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl border ${cls}`}><Icon className="h-4 w-4" /></span>
          <div className="min-w-0">
            <p data-testid="devices-row-name" className="truncate text-sm font-semibold text-txt">{d.name}</p>
            <Link to={`/?store=${d.store_id}`} data-testid="devices-row-store" className="inline-flex items-center gap-1 text-xs text-txt-2 hover:text-emerald-brand hover:underline">
              <Store className="h-3 w-3" aria-hidden="true" /> {d.store_name}
            </Link>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Cell label="Heartbeat" testId="devices-row-heartbeat">{when(d.last_heartbeat_at, "belum pernah")}</Cell>
          <Cell label="Event terakhir" testId="devices-row-last-event">{when(d.last_event_at, "belum ada")}</Cell>
          <Cell label="Tertunda" testId="devices-row-pending">{d.pending_events ?? "—"}{d.last_frame_age_s !== null && ` · frame ${Math.round(d.last_frame_age_s)} dtk`}</Cell>
          <Cell label="Agent" testId="devices-row-agent">{d.agent_version ?? "—"}</Cell>
        </div>
        <div className="flex items-center gap-2">
          <span data-testid="devices-row-badge" data-status={st}
            className={`inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${cls}`}>
            <Icon className="h-3.5 w-3.5" aria-hidden="true" />{label}
          </span>
          <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label={open ? "Tutup riwayat heartbeat" : "Lihat riwayat heartbeat 24 jam"}
            data-testid="devices-row-history-toggle" className="ctl ctl-ghost h-8 w-8 min-w-8 px-0 text-txt-2">
            <ChevronDown className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden="true" />
          </button>
        </div>
      </div>
      {open && <div className="border-t border-line bg-surface-2/40 px-4 py-4 sm:pl-16"><HeartbeatTimeline deviceId={d.device_id} tz={tz} /></div>}
    </li>
  );
};
