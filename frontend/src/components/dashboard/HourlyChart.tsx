import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { HourlyOut } from "../../api/types";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { hourLabel } from "../../lib/time";

interface Props {
  hourly: HourlyOut | undefined;
}

interface Row {
  hour: string;
  masuk: number;
  keluar: number;
}

const COLORS = { masuk: "#047857", keluar: "#64748B" } as const;
const LABELS = { masuk: "Orang masuk", keluar: "Orang keluar" } as const;
const TICK = { fill: "#52525B", fontSize: 11, fontFamily: "Manrope" };

const ChartTooltip = ({ active, payload, label }: { active?: boolean; payload?: { value: number; name: string }[]; label?: string }) => {
  if (!active || !payload?.length) return null;
  return (
    <div data-testid="hourly-chart-tooltip" className="card px-3 py-2 text-xs">
      <p className="mb-1 font-medium text-txt">{label}:00 – {label}:59</p>
      {payload.map((e) => (
        <p key={e.name} className="flex items-center gap-2 text-txt-2">
          <span className="h-2 w-2 rounded-full" style={{ background: COLORS[e.name as keyof typeof COLORS] }} />
          {LABELS[e.name as keyof typeof LABELS]}: <span className="tnum font-semibold text-txt">{e.value}</span>
        </p>
      ))}
    </div>
  );
};

const Legend = () => (
  <ul className="flex items-center gap-4 text-xs text-txt-2" aria-label="Legenda">
    {(Object.keys(COLORS) as (keyof typeof COLORS)[]).map((k) => (
      <li key={k} className="flex items-center gap-1.5">
        <span aria-hidden="true" className="h-2.5 w-2.5 rounded-sm" style={{ background: COLORS[k] }} />
        {LABELS[k]}
      </li>
    ))}
  </ul>
);

export const HourlyChart = ({ hourly }: Props) => {
  const narrow = useMediaQuery("(max-width: 640px)");
  const rows: Row[] = (hourly?.buckets ?? []).map((b) => ({ hour: hourLabel(b.hour_start), masuk: b.enter, keluar: b.exit }));
  const total = rows.reduce((a, r) => a + r.masuk + r.keluar, 0);
  return (
    <section data-testid="hourly-chart-container" aria-labelledby="hourly-title" className="card fade-in p-5 sm:p-6">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id="hourly-title" className="text-base md:text-lg font-semibold text-txt">Kunjungan per jam</h2>
          <p className="text-xs text-txt-3">{hourly ? `${hourly.date} · zona waktu ${hourly.timezone}` : "Data per jam belum tersedia"}</p>
        </div>
        <Legend />
      </div>
      {hourly && total === 0 && (
        <p data-testid="hourly-empty-note" className="mb-3 rounded-ctl bg-surface-2 px-3 py-2 text-xs text-txt-2">
          Data berhasil dimuat: semua jam bernilai 0 pada tanggal ini.
        </p>
      )}
      {!hourly && (
        <p data-testid="hourly-unavailable-note" className="mb-3 rounded-ctl bg-surface-2 px-3 py-2 text-xs text-txt-2">
          Grafik kosong karena data belum berhasil dimuat, bukan karena nilai 0.
        </p>
      )}
      <div className="h-64 sm:h-72">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 8, right: 4, left: -20, bottom: 0 }} barCategoryGap="20%" barGap={2}>
            <CartesianGrid vertical={false} stroke="#E4E4E7" strokeDasharray="3 3" />
            <XAxis dataKey="hour" tick={TICK} axisLine={false} tickLine={false} interval={narrow ? 2 : 0} />
            <YAxis allowDecimals={false} tick={TICK} axisLine={false} tickLine={false} width={44} />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(24,24,27,0.04)" }} />
            <Bar dataKey="masuk" name="masuk" fill={COLORS.masuk} radius={[3, 3, 0, 0]} />
            <Bar dataKey="keluar" name="keluar" fill={COLORS.keluar} radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      {narrow && <p className="mt-2 text-[11px] text-txt-3">Label jam ditampilkan setiap 3 jam; sentuh batang untuk melihat jam persisnya.</p>}
    </section>
  );
};
