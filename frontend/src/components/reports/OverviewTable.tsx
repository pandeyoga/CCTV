import { Link } from "react-router-dom";
import { AlertTriangle, ArrowRight, CheckCircle2 } from "lucide-react";
import type { StoreOverviewOut } from "../../api/types";
import { useOverview } from "../../hooks/useDashboardData";
import { formatPct, pctChange } from "../../lib/report";
import { relativeTime } from "../../lib/time";

const Th = ({ children, right = false }: { children: string; right?: boolean }) => (
  <th scope="col" className={`px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-txt-3 ${right ? "text-right" : "text-left"}`}>{children}</th>
);

const Row = ({ s, now, onPick }: { s: StoreOverviewOut; now: Date; onPick: (id: string) => void }) => {
  const vsYesterday = pctChange(s.enter, s.yesterday_enter);
  const cls = vsYesterday === null || vsYesterday === 0 ? "text-txt-2" : vsYesterday > 0 ? "text-emerald-brand" : "text-danger";
  return (
    <tr data-testid="overview-row" className="border-t border-line transition-colors hover:bg-surface-2/60">
      <td className="px-4 py-3">
        <button type="button" onClick={() => onPick(s.store_id)} data-testid="overview-store-pick" className="text-left text-sm font-semibold text-txt hover:text-emerald-brand hover:underline">{s.name}</button>
        <p className="text-[11px] text-txt-3">{s.timezone} · {s.date}{s.open_time && <> · <span data-testid="overview-open-state" data-open={s.is_open_now} className={s.is_open_now ? "text-emerald-brand" : "text-txt-2"}>{s.is_open_now ? "buka" : "tutup"} ({s.open_time}–{s.close_time})</span></>}</p>
      </td>
      <td data-testid="overview-enter" className="tnum px-4 py-3 text-right text-base font-semibold text-txt">{s.enter}</td>
      <td data-testid="overview-exit" className="tnum px-4 py-3 text-right text-sm text-txt-2">{s.exit}</td>
      <td className={`tnum px-4 py-3 text-right text-sm font-medium ${cls}`} data-testid="overview-vs-yesterday" title={`Kemarin: ${s.yesterday_enter}`}>{formatPct(vsYesterday)}</td>
      <td data-testid="overview-avg7" className="tnum px-4 py-3 text-right text-sm text-txt-2">{s.avg_enter_7d.toLocaleString("id-ID", { maximumFractionDigits: 1 })}</td>
      <td className="px-4 py-3 text-right text-xs text-txt-2">{s.last_event_at ? relativeTime(s.last_event_at, now) : "belum ada"}</td>
      <td className="px-4 py-3 text-right">
        <span data-testid="overview-devices" data-problem={s.devices_problem > 0}
          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium tnum ${s.devices_problem > 0 ? "border-amber-200 bg-warn-soft text-warn" : s.devices_total > 0 ? "border-emerald-200 bg-emerald-soft text-emerald-brand" : "border-line bg-surface-2 text-txt-2"}`}>
          {s.devices_problem > 0 ? <AlertTriangle className="h-3 w-3" /> : <CheckCircle2 className="h-3 w-3" />}
          {s.devices_problem > 0 ? `${s.devices_problem}/${s.devices_total} bermasalah` : !s.is_open_now && s.devices_total > 0 ? `${s.devices_total} perangkat · toko tutup` : `${s.devices_total} perangkat`}
        </span>
      </td>
    </tr>
  );
};

export const OverviewTable = ({ now, onPick }: { now: Date; onPick: (id: string) => void }) => {
  const q = useOverview();
  const total = (q.data ?? []).reduce((a, s) => a + s.enter, 0);
  return (
    <section data-testid="overview-table" className="card fade-in overflow-hidden">
      <header className="flex flex-wrap items-end justify-between gap-2 px-5 py-4">
        <div>
          <h2 className="text-base md:text-lg font-semibold text-txt">Semua toko hari ini</h2>
          <p className="text-xs text-txt-3">{q.data ? `${q.data.length} toko · ${total} orang masuk hari ini (menurut zona waktu masing-masing toko)` : "Memuat…"}</p>
        </div>
        <Link to="/perangkat" className="inline-flex items-center gap-1 text-xs font-medium text-txt-2 hover:text-emerald-brand" data-testid="overview-devices-link">Lihat perangkat <ArrowRight className="h-3 w-3" /></Link>
      </header>
      {q.isError && !q.data && <p className="px-5 pb-4 text-sm text-danger">{(q.error as Error).message}</p>}
      {q.data && q.data.length === 0 && <p data-testid="overview-empty" className="px-5 pb-4 text-sm text-txt-2">Belum ada toko yang dapat Anda akses.</p>}
      {q.data && q.data.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px]">
            <thead><tr><Th>Toko</Th><Th right>Masuk</Th><Th right>Keluar</Th><Th right>vs kemarin</Th><Th right>Rata-rata 7 hari</Th><Th right>Event terakhir</Th><Th right>Perangkat</Th></tr></thead>
            <tbody>{q.data.map((s) => <Row key={s.store_id} s={s} now={now} onPick={onPick} />)}</tbody>
          </table>
        </div>
      )}
    </section>
  );
};
