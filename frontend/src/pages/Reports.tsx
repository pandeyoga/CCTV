import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Download, Store } from "lucide-react";
import { AppShell } from "../components/dashboard/AppShell";
import { ErrorState, NoStores, StaleBanner } from "../components/dashboard/States";
import { DailyChart } from "../components/reports/DailyChart";
import { OverviewTable } from "../components/reports/OverviewTable";
import { BusiestHours, ReportKpis } from "../components/reports/ReportKpis";
import { useRangeReport, useStores } from "../hooks/useDashboardData";
import { useNow } from "../hooks/useNow";
import { dailyCsv, downloadText } from "../lib/report";
import { addDays, formatDateLong, todayInTz } from "../lib/time";

type Preset = "7" | "30" | "custom";
const PRESETS: { id: Preset; label: string }[] = [{ id: "7", label: "7 hari" }, { id: "30", label: "30 hari" }, { id: "custom", label: "Kustom" }];
const MAX_DAYS = 92;

const daysBetween = (a: string, b: string) => Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86_400_000) + 1;

export default function Reports() {
  const now = useNow();
  const stores = useStores();
  const [params, setParams] = useSearchParams();
  const [storeId, setStoreId] = useState<string | undefined>(params.get("store") ?? undefined);
  const store = useMemo(() => stores.data?.find((s) => s.store_id === storeId) ?? stores.data?.[0], [stores.data, storeId]);
  useEffect(() => { if (store && store.store_id !== storeId) setStoreId(store.store_id); }, [store, storeId]);
  const tz = store?.timezone ?? "UTC";
  const today = todayInTz(tz, now);

  const [preset, setPreset] = useState<Preset>("7");
  const [custom, setCustom] = useState<{ from: string; to: string } | null>(null);
  const range = preset === "custom" && custom ? custom : { from: addDays(today, -(Number(preset === "custom" ? 7 : preset) - 1)), to: today };
  const days = daysBetween(range.from, range.to);
  const rangeError = range.to < range.from ? "Tanggal akhir harus setelah tanggal mulai" : days > MAX_DAYS ? `Maksimal ${MAX_DAYS} hari` : range.to > today ? "Tanggal akhir tidak boleh melewati hari ini" : null;
  const report = useRangeReport(rangeError ? undefined : store?.store_id, range.from, range.to);

  const pickStore = (id: string) => { setStoreId(id); setParams((p) => { p.set("store", id); return p; }, { replace: true }); };
  const exportCsv = () => report.data && store && downloadText(`laporan_${store.name.replace(/[^\w-]+/g, "_")}_${range.from}_${range.to}.csv`, dailyCsv(report.data, store.name));

  const body = () => {
    if (stores.isPending) return <div className="card h-40 animate-pulse" aria-hidden="true" />;
    if (!stores.data) return <ErrorState message={(stores.error as Error).message} onRetry={() => void stores.refetch()} />;
    if (stores.data.length === 0) return <NoStores />;
    return (
      <>
        <OverviewTable now={now} onPick={pickStore} />
        <div className="glass rounded-card flex flex-wrap items-center gap-3 p-3" data-testid="report-toolbar">
          <label className="ctl h-10 gap-2 pr-2 text-xs">
            <Store className="h-4 w-4 text-txt-2" aria-hidden="true" /><span className="sr-only">Toko</span>
            <select value={store?.store_id ?? ""} onChange={(e) => pickStore(e.target.value)} className="max-w-[14rem] bg-transparent text-sm font-medium text-txt focus:outline-none" data-testid="report-store-select">
              {stores.data.map((s) => <option key={s.store_id} value={s.store_id}>{s.name}</option>)}
            </select>
          </label>
          <div role="group" aria-label="Rentang" className="flex items-center gap-1">
            {PRESETS.map((p) => (
              <button key={p.id} type="button" onClick={() => { setPreset(p.id); if (p.id === "custom" && !custom) setCustom({ from: range.from, to: range.to }); }}
                aria-pressed={preset === p.id} data-testid={`report-preset-${p.id}`} className={`ctl h-10 text-xs ${preset === p.id ? "ctl-ink" : ""}`}>{p.label}</button>
            ))}
          </div>
          {preset === "custom" && custom && (
            <div className="flex flex-wrap items-center gap-2 text-xs text-txt-2">
              <input type="date" value={custom.from} max={today} onChange={(e) => setCustom({ ...custom, from: e.target.value })} className="ctl h-10 text-xs" data-testid="report-from-input" aria-label="Dari" />
              <span>s.d.</span>
              <input type="date" value={custom.to} max={today} onChange={(e) => setCustom({ ...custom, to: e.target.value })} className="ctl h-10 text-xs" data-testid="report-to-input" aria-label="Sampai" />
            </div>
          )}
          <button type="button" onClick={exportCsv} disabled={!report.data} className="ctl h-10 sm:ml-auto" data-testid="report-export-csv"><Download className="h-4 w-4" /> Ekspor CSV</button>
        </div>
        {rangeError && <p role="alert" data-testid="report-range-error" className="card border-amber-200 bg-warn-soft p-4 text-sm text-warn">{rangeError}</p>}
        {!rangeError && report.isPending && <div className="card h-64 animate-pulse" aria-hidden="true" />}
        {!rangeError && report.isError && !report.data && <ErrorState message={(report.error as Error).message} onRetry={() => void report.refetch()} />}
        {report.data && (
          <>
            {report.isError && <StaleBanner message={(report.error as Error).message} onRetry={() => void report.refetch()} />}
            <p data-testid="report-range-label" className="text-sm text-txt-2"><span className="font-medium text-txt">{store?.name}</span> · {formatDateLong(range.from)} – {formatDateLong(range.to)} ({days} hari)
              {report.data.open_time && <span data-testid="report-hours-note" className="ml-2 rounded-full border border-line bg-surface px-2 py-0.5 text-[11px]">jam operasional {report.data.open_time}–{report.data.close_time}{report.data.outside_hours_excluded > 0 && ` · ${report.data.outside_hours_excluded} event di luar jam tidak dihitung`}</span>}
            </p>
            <ReportKpis r={report.data} />
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3 md:gap-6">
              <div className="lg:col-span-2"><DailyChart report={report.data} /></div>
              <BusiestHours r={report.data} />
            </div>
          </>
        )}
      </>
    );
  };

  return (
    <AppShell>
      <main data-testid="reports-page" className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-txt">Laporan</h1>
          <p className="mt-1 text-sm text-txt-2">Semua toko sekali lihat, lalu tren harian, perbandingan periode dan jam tersibuk per toko.</p>
        </div>
        {body()}
        <footer className="pt-2 text-xs text-txt-3">Periode pembanding = periode sebelumnya dengan panjang yang sama. Hari dihitung dalam zona waktu toko ({tz}).</footer>
      </main>
    </AppShell>
  );
}
