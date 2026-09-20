import { Check, CheckCheck, Cpu, Store } from "lucide-react";
import { Link } from "react-router-dom";
import type { AlertOut } from "../../api/types";
import { ALERT_RULE, ALERT_SEVERITY, durationLabel } from "../../lib/alerts";
import { formatDateTimeInTz, relativeTime } from "../../lib/time";

interface Props {
  a: AlertOut;
  now: Date;
  canAck: boolean;
  onAck: (id: string) => void;
  acking: boolean;
}

export const AlertRow = ({ a, now, canAck, onAck, acking }: Props) => {
  const rule = ALERT_RULE[a.rule];
  const sev = ALERT_SEVERITY[a.severity];
  const open = a.resolved_at === null;
  const tz = a.store_timezone;
  return (
    <li data-testid="alert-row" data-rule={a.rule} data-severity={a.severity} data-open={open}
      className={`fade-in grid gap-3 border-l-4 p-4 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:items-start ${open ? sev.bar : "border-l-zinc-300"}`}>
      <span aria-hidden="true" className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl border ${open ? sev.cls : "border-line bg-surface-2 text-txt-2"}`}>
        <rule.Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <p data-testid="alert-row-title" className="text-sm font-semibold text-txt">{rule.label}</p>
          <span data-testid="alert-row-severity" className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${open ? sev.cls : "border-line bg-surface-2 text-txt-2"}`}>
            {open ? sev.label : "Selesai"}
          </span>
          {a.acknowledged_at && (
            <span data-testid="alert-row-acked" className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-soft px-2 py-0.5 text-[11px] font-medium text-emerald-brand">
              <CheckCheck className="h-3 w-3" aria-hidden="true" /> Dilihat{a.acknowledged_by_email ? ` · ${a.acknowledged_by_email}` : ""}
            </span>
          )}
        </div>
        <p data-testid="alert-row-message" className="text-sm text-txt-2">{a.message}</p>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-txt-3 tnum">
          <Link to={`/?store=${a.store_id}`} data-testid="alert-row-store" className="inline-flex items-center gap-1 hover:text-emerald-brand hover:underline"><Store className="h-3 w-3" aria-hidden="true" />{a.store_name}</Link>
          {a.device_name && <Link to="/perangkat" data-testid="alert-row-device" className="inline-flex items-center gap-1 hover:text-emerald-brand hover:underline"><Cpu className="h-3 w-3" aria-hidden="true" />{a.device_name}</Link>}
          <span data-testid="alert-row-opened">Mulai {formatDateTimeInTz(a.opened_at, tz)} ({relativeTime(a.opened_at, now)})</span>
          <span data-testid="alert-row-duration">{open ? `berlangsung ${durationLabel(a.opened_at, null, now)}` : `selesai ${formatDateTimeInTz(a.resolved_at!, tz)} · durasi ${durationLabel(a.opened_at, a.resolved_at, now)}`}</span>
        </p>
      </div>
      {open && canAck && !a.acknowledged_at && (
        <button type="button" onClick={() => onAck(a.alert_id)} disabled={acking} data-testid="alert-row-ack" className="ctl h-9 self-center">
          <Check className="h-4 w-4" aria-hidden="true" /> Tandai dilihat
        </button>
      )}
    </li>
  );
};
