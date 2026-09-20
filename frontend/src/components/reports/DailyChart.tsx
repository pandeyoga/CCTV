import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { RangeReportOut } from "../../api/types";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { formatDateLong } from "../../lib/time";

const COLORS = { masuk: "#047857", keluar: "#64748B" } as const;
const LABELS = { masuk: "Orang masuk", keluar: "Orang keluar" } as const;
const TICK = { fill: "#52525B", fontSize: 11, fontFamily: "Manrope" };

const shortDate = (ymd: string) => new Date(`${ymd}T00:00:00`).toLocaleDateString("id-ID", { day: "2-digit", month: "short" });

const ChartTooltip = ({ active, payload, label }: { active?: boolean; payload?: { value: number; name: string }[]; label?: string }) => {
  if (!active || !payload?.length || !label) return null;
  return (
    <div data-testid="daily-chart-tooltip" className="card px-3 py-2 text-xs">
      <p className="mb-1 font-medium text-txt">{formatDateLong(label)}</p>
      {payload.map((e) => (
        <p key={e.name} className="flex items-center gap-2 text-txt-2">
          <span className="h-2 w-2 rounded-full" style={{ background: COLORS[e.name as keyof typeof COLORS] }} />
          {LABELS[e.name as keyof typeof LABELS]}: <span className="tnum font-semibold text-txt">{e.value}</span>
        </p>
      ))}
    </div>
  );
};

export const DailyChart = ({ report }: { report: RangeReportOut }) => {
  const narrow = useMediaQuery("(max-width: 640px)");
  const rows = report.daily.map((d) => ({ date: d.date, masuk: d.enter, keluar: d.exit }));
  const total = report.current.enter + report.current.exit;
  const interval = Math.max(0, Math.ceil(rows.length / (narrow ? 6 : 16)) - 1);
  return (
    <section data-testid="daily-chart-container" className="card fade-in p-5 sm:p-6">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-base md:text-lg font-semibold text-txt">Kunjungan per hari</h2>
          <p className="text-xs text-txt-3">{report.current.days} hari · zona waktu {report.timezone}</p>
        </div>
        <ul className="flex items-center gap-4 text-xs text-txt-2" aria-label="Legenda">
          {(Object.keys(COLORS) as (keyof typeof COLORS)[]).map((k) => (
            <li key={k} className="flex items-center gap-1.5"><span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm" style={{ background: COLORS[k] }} />{LABELS[k]}</li>
          ))}
        </ul>
      </div>
      {total === 0 && <p data-testid="daily-empty-note" className="mb-3 rounded-ctl bg-surface-2 px-3 py-2 text-xs text-txt-2">Data berhasil dimuat: tidak ada event pada rentang ini (nilai nyata 0).</p>}
      <div className="h-64 sm:h-72">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 8, right: 4, left: -20, bottom: 0 }} barCategoryGap="25%" barGap={2}>
            <CartesianGrid vertical={false} stroke="#E4E4E7" strokeDasharray="3 3" />
            <XAxis dataKey="date" tickFormatter={shortDate} tick={TICK} axisLine={false} tickLine={false} interval={interval} />
            <YAxis allowDecimals={false} tick={TICK} axisLine={false} tickLine={false} width={44} />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(24,24,27,0.04)" }} />
            <Bar dataKey="masuk" name="masuk" fill={COLORS.masuk} radius={[3, 3, 0, 0]} />
            <Bar dataKey="keluar" name="keluar" fill={COLORS.keluar} radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
};
