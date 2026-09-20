import { Shapes } from "lucide-react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import type { ZoneOccupancyOut, ZoneOut, ZoneSeriesOut } from "../../api/types";
import { formatDateTimeInTz, relativeTime } from "../../lib/time";

interface Props {
  zones: ZoneOut[] | undefined;
  occupancy: ZoneOccupancyOut | undefined;
  tz: string;
  now: Date;
  date: string;
}

const STALE_S = 120; // 12 × 10 s sampling interval

const ZoneCard = ({ z, series, tz, now }: { z: ZoneOut; series: ZoneSeriesOut | undefined; tz: string; now: Date }) => {
  const ageS = z.last_sample_ts ? (now.getTime() - new Date(z.last_sample_ts).getTime()) / 1000 : null;
  const live = ageS !== null && ageS <= STALE_S;
  const data = (series?.buckets ?? []).map((b) => ({ h: new Date(b.hour_start).getHours(), avg: b.avg_count, max: b.max_count, n: b.samples }));
  return (
    <li data-testid="zone-card" data-live={live} className="rounded-xl border border-line bg-surface-2/60 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p data-testid="zone-card-name" className="truncate text-sm font-semibold text-txt">{z.name}</p>
          <p className="truncate text-[11px] text-txt-3"><code className="font-mono">{z.external_id}</code> · kamera {z.camera_external_id}</p>
        </div>
        <div className="text-right">
          <p data-testid="zone-card-count" className={`tnum text-2xl font-semibold leading-none ${live ? "text-txt" : "text-txt-3"}`}>{live ? z.last_count : "—"}</p>
          <p className="text-[11px] text-txt-3">orang sekarang</p>
        </div>
      </div>
      <p data-testid="zone-card-last" className="mt-2 text-[11px] text-txt-3">
        {z.last_sample_ts ? `Sampel terakhir ${relativeTime(z.last_sample_ts, now)} · ${formatDateTimeInTz(z.last_sample_ts, tz)}${live ? "" : " (tidak ada data baru)"}` : "Belum ada sampel dari edge agent"}
        {series && series.samples > 0 && <> · puncak hari ini <span className="tnum font-medium text-txt-2" data-testid="zone-card-peak">{series.peak}</span></>}
      </p>
      <div className="mt-3 h-16" data-testid="zone-card-chart">
        {series && series.samples > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 2, right: 0, bottom: 0, left: 0 }} barCategoryGap={1}>
              <XAxis dataKey="h" hide />
              <Tooltip cursor={{ fill: "rgba(0,0,0,0.04)" }} content={({ active, payload }) => active && payload?.length ? (
                <div className="glass rounded-lg px-2 py-1 text-[11px] text-txt shadow">
                  {String(payload[0].payload.h).padStart(2, "0")}:00 · rata-rata {payload[0].payload.avg} · maks {payload[0].payload.max} · {payload[0].payload.n} sampel
                </div>) : null} />
              <Bar dataKey="avg" fill="var(--emerald)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        ) : <p className="pt-5 text-center text-[11px] text-txt-3">Belum ada sampel pada tanggal ini</p>}
      </div>
    </li>
  );
};

export const ZonePanel = ({ zones, occupancy, tz, now, date }: Props) => {
  if (zones && zones.length === 0) return null; // stores without zones keep the classic dashboard
  const byId = new Map((occupancy?.zones ?? []).map((s) => [s.zone_id, s]));
  return (
    <section data-testid="zone-panel" aria-labelledby="zones-title" className="card fade-in p-5 sm:p-6">
      <div className="mb-4 flex items-start gap-3">
        <span aria-hidden="true" className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-surface-2 text-txt-2"><Shapes className="h-4 w-4" /></span>
        <div>
          <h2 id="zones-title" className="text-base md:text-lg font-semibold text-txt">Okupansi zona</h2>
          <p className="text-xs text-txt-3">Jumlah orang di dalam tiap zona (sampel tiap 10 dtk dari edge agent) · rata-rata per jam untuk {date}. Track ID bukan identitas orang.</p>
        </div>
      </div>
      {!zones && <p data-testid="zone-unavailable" className="text-sm text-txt-2">Daftar zona belum berhasil dimuat.</p>}
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="zone-list">
        {(zones ?? []).map((z) => <ZoneCard key={z.zone_id} z={z} series={byId.get(z.zone_id)} tz={tz} now={now} />)}
      </ul>
    </section>
  );
};
