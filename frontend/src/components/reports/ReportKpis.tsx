import type { ReactNode } from "react";
import { ArrowDownRight, ArrowUpRight, CalendarDays, Clock3, LogIn, LogOut, Minus } from "lucide-react";
import type { RangeReportOut } from "../../api/types";
import { busiestHours, formatPct, hourRange, pctChange, peakDay } from "../../lib/report";
import { formatDateLong } from "../../lib/time";

const Delta = ({ current, previous, testId }: { current: number; previous: number; testId: string }) => {
  const p = pctChange(current, previous);
  const Icon = p === null || p === 0 ? Minus : p > 0 ? ArrowUpRight : ArrowDownRight;
  const cls = p === null || p === 0 ? "bg-surface-2 text-txt-2" : p > 0 ? "bg-emerald-soft text-emerald-brand" : "bg-danger-soft text-danger";
  return (
    <span data-testid={testId} className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium tnum ${cls}`} title={`Periode sebelumnya: ${previous}`}>
      <Icon className="h-3 w-3" aria-hidden="true" /> {formatPct(p)}
    </span>
  );
};

const Card = ({ label, value, hint, icon, chip, testId, extra }: { label: string; value: string; hint: string; icon: ReactNode; chip: string; testId: string; extra?: ReactNode }) => (
  <article className="card fade-in flex flex-col gap-3 p-5">
    <div className="flex items-center justify-between gap-3">
      <h2 className="text-sm font-medium text-txt-2">{label}</h2>
      <span aria-hidden="true" className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${chip}`}>{icon}</span>
    </div>
    <div className="flex flex-wrap items-end gap-2">
      <p data-testid={testId} className="tnum text-3xl sm:text-4xl font-semibold tracking-tight text-txt leading-none">{value}</p>
      {extra}
    </div>
    <p className="text-xs text-txt-3 leading-relaxed">{hint}</p>
  </article>
);

export const ReportKpis = ({ r }: { r: RangeReportOut }) => {
  const avg = r.current.enter / r.current.days;
  const peak = peakDay(r);
  const top = busiestHours(r, 1)[0];
  const prev = `vs ${formatDateLong(r.previous.from_date)} – ${formatDateLong(r.previous.to_date)}`;
  return (
    <div data-testid="report-kpis" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Card label="Total masuk" value={r.current.enter.toLocaleString("id-ID")} hint={prev} testId="report-kpi-enter"
        icon={<LogIn className="h-4 w-4 text-emerald-brand" />} chip="bg-emerald-soft" extra={<Delta current={r.current.enter} previous={r.previous.enter} testId="report-delta-enter" />} />
      <Card label="Total keluar" value={r.current.exit.toLocaleString("id-ID")} hint={prev} testId="report-kpi-exit"
        icon={<LogOut className="h-4 w-4 text-exit" />} chip="bg-exit-soft" extra={<Delta current={r.current.exit} previous={r.previous.exit} testId="report-delta-exit" />} />
      <Card label="Rata-rata masuk / hari" value={avg.toLocaleString("id-ID", { maximumFractionDigits: 1 })} testId="report-kpi-avg"
        hint={peak ? `Hari tersibuk: ${formatDateLong(peak.date)} (${peak.enter} masuk)` : "Belum ada hari dengan pengunjung masuk"}
        icon={<CalendarDays className="h-4 w-4 text-txt-2" />} chip="bg-surface-2" />
      <Card label="Jam tersibuk" value={top ? hourRange(top.hour) : "—"} testId="report-kpi-peak-hour"
        hint={top ? `${top.enter} orang masuk pada jam ini sepanjang rentang` : "Tidak ada jam dengan pengunjung masuk"}
        icon={<Clock3 className="h-4 w-4 text-txt-2" />} chip="bg-surface-2" />
    </div>
  );
};

export const BusiestHours = ({ r }: { r: RangeReportOut }) => {
  const rows = busiestHours(r, 6);
  const max = rows[0]?.enter ?? 0;
  return (
    <section data-testid="busiest-hours" className="card fade-in p-5 sm:p-6">
      <h2 className="text-base md:text-lg font-semibold text-txt">Jam tersibuk</h2>
      <p className="mb-4 text-xs text-txt-3">Jumlah orang masuk per jam, dijumlahkan sepanjang rentang.</p>
      {rows.length === 0 && <p data-testid="busiest-hours-empty" className="rounded-ctl bg-surface-2 px-3 py-2 text-xs text-txt-2">Tidak ada pengunjung masuk pada rentang ini.</p>}
      <ol className="space-y-2.5">
        {rows.map((h, i) => (
          <li key={h.hour} data-testid="busiest-hour-row" className="grid grid-cols-[1.5rem_6.5rem_1fr_3rem] items-center gap-2 text-sm">
            <span className="tnum text-xs text-txt-3">{i + 1}.</span>
            <span className="tnum font-medium text-txt">{hourRange(h.hour)}</span>
            <span className="h-2 overflow-hidden rounded-full bg-surface-2"><span className="block h-full rounded-full bg-emerald-brand" style={{ width: `${max ? (h.enter / max) * 100 : 0}%` }} /></span>
            <span className="tnum text-right text-txt-2">{h.enter}</span>
          </li>
        ))}
      </ol>
    </section>
  );
};
