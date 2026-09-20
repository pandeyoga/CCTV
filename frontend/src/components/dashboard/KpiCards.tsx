import type { ReactNode } from "react";
import { ArrowLeftRight, Clock, LogIn, LogOut } from "lucide-react";
import type { SummaryOut } from "../../api/types";
import { formatTimeInTz, relativeTime } from "../../lib/time";

interface CardProps {
  testId: string;
  label: string;
  value: string;
  hint: string;
  chip: string;
  icon: ReactNode;
}

const KpiCard = ({ testId, label, value, hint, chip, icon }: CardProps) => (
  <article className="card fade-in p-5 sm:p-6 flex flex-col gap-3">
    <div className="flex items-center justify-between gap-3">
      <h2 className="text-sm font-medium text-txt-2">{label}</h2>
      <span aria-hidden="true" className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${chip}`}>{icon}</span>
    </div>
    <p data-testid={testId} className="tnum text-4xl sm:text-5xl font-semibold tracking-tight text-txt leading-none">{value}</p>
    <p className="text-xs text-txt-3 leading-relaxed">{hint}</p>
  </article>
);

interface Props {
  summary: SummaryOut | undefined;
  tz: string;
  now: Date;
}

export const KpiCards = ({ summary, tz, now }: Props) => {
  const v = (n: number | undefined) => (n === undefined ? "—" : n.toLocaleString("id-ID"));
  const net = summary === undefined ? undefined : summary.enter - summary.exit;
  const last = summary?.last_event_at ?? null;
  return (
    <section data-testid="kpi-section" aria-label="Ringkasan angka" className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 md:gap-6">
      <KpiCard testId="kpi-enter-count" label="Orang masuk" value={v(summary?.enter)}
        hint="Jumlah crossing masuk pada tanggal terpilih" chip="bg-emerald-soft text-emerald-brand" icon={<LogIn className="h-4 w-4" />} />
      <KpiCard testId="kpi-exit-count" label="Orang keluar" value={v(summary?.exit)}
        hint="Jumlah crossing keluar pada tanggal terpilih" chip="bg-exit-soft text-exit" icon={<LogOut className="h-4 w-4" />} />
      <KpiCard testId="kpi-net-count" label="Selisih masuk–keluar"
        value={net === undefined ? "—" : net > 0 ? `+${net.toLocaleString("id-ID")}` : net.toLocaleString("id-ID")}
        hint="Masuk dikurangi keluar untuk tanggal terpilih; bukan jumlah orang di dalam toko"
        chip="bg-surface-2 text-txt-2" icon={<ArrowLeftRight className="h-4 w-4" />} />
      <KpiCard testId="kpi-last-event-at" label="Event terakhir" value={last ? formatTimeInTz(last, tz) : "—"}
        hint={last ? `${relativeTime(last, now)} · waktu toko` : "Belum ada event yang diterima untuk toko ini"}
        chip="bg-surface-2 text-txt-2" icon={<Clock className="h-4 w-4" />} />
    </section>
  );
};
