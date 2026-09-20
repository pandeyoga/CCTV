import { useMemo, useState } from "react";
import { Cpu, RefreshCw, Search } from "lucide-react";
import { AppShell } from "../components/dashboard/AppShell";
import { ErrorState, StaleBanner } from "../components/dashboard/States";
import { DeviceRow } from "../components/devices/DeviceRow";
import { StatusFilter, type Filter } from "../components/devices/StatusFilter";
import { useAllDevices } from "../hooks/useDashboardData";
import { useNow } from "../hooks/useNow";
import { DEVICE_STATUS_ORDER, statusOf, type DeviceStatus } from "../lib/deviceStatus";
import { relativeTime } from "../lib/time";

const Bone = ({ className }: { className: string }) => <div aria-hidden="true" className={`animate-pulse rounded-lg bg-zinc-200/80 ${className}`} />;

export default function Devices() {
  const now = useNow();
  const q = useAllDevices();
  const [filter, setFilter] = useState<Filter>("problem");
  const [search, setSearch] = useState("");

  const rows = useMemo(() => (q.data ?? []).map((d) => ({ d, st: statusOf(d, now) })), [q.data, now]);
  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: rows.length, problem: 0, camera_down: 0, stale: 0, unknown: 0, connected: 0, inactive: 0 };
    for (const { st } of rows) { c[st] += 1; if (st === "camera_down" || st === "stale") c.problem += 1; }
    return c;
  }, [rows]);

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return rows
      .filter(({ st }) => filter === "all" || (filter === "problem" ? st === "camera_down" || st === "stale" : st === filter))
      .filter(({ d }) => !needle || d.name.toLowerCase().includes(needle) || d.store_name.toLowerCase().includes(needle))
      .sort((a, b) => DEVICE_STATUS_ORDER.indexOf(a.st) - DEVICE_STATUS_ORDER.indexOf(b.st) || a.d.store_name.localeCompare(b.d.store_name) || a.d.name.localeCompare(b.d.name));
  }, [rows, filter, search]);

  const body = () => {
    if (q.isPending) return (
      <div data-testid="devices-skeleton" role="status" aria-label="Memuat perangkat" className="card divide-y divide-line">
        {[0, 1, 2].map((i) => <div key={i} className="flex items-center gap-4 p-4"><Bone className="h-9 w-9 rounded-xl" /><div className="flex-1 space-y-2"><Bone className="h-4 w-40" /><Bone className="h-3 w-64" /></div><Bone className="h-6 w-28 rounded-full" /></div>)}
      </div>
    );
    if (!q.data) return <ErrorState message={(q.error as Error).message} onRetry={() => void q.refetch()} />;
    return (
      <>
        {q.isError && <StaleBanner message={(q.error as Error).message} onRetry={() => void q.refetch()} />}
        {rows.length === 0 && (
          <div data-testid="devices-empty" className="card p-6 text-sm text-txt-2">Belum ada perangkat terdaftar pada toko yang dapat Anda akses.</div>
        )}
        {rows.length > 0 && visible.length === 0 && (
          <div data-testid="devices-filter-empty" className="card p-6 text-sm text-txt-2">
            {filter === "problem" && !search ? "Tidak ada perangkat bermasalah saat ini." : "Tidak ada perangkat yang cocok dengan filter ini."}
          </div>
        )}
        {visible.length > 0 && (
          <ul data-testid="devices-table" className="card divide-y divide-line overflow-hidden">
            {visible.map(({ d, st }) => <DeviceRow key={d.device_id} d={d} st={st as DeviceStatus} now={now} />)}
          </ul>
        )}
      </>
    );
  };

  return (
    <AppShell>
      <main data-testid="devices-page" className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-txt">Perangkat</h1>
            <p className="mt-1 text-sm text-txt-2">Semua edge device di toko yang dapat Anda akses, dengan status heartbeat terkini.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-txt-2">
            <span data-testid="devices-updated" className="rounded-full border border-line bg-surface px-2.5 py-1">
              {q.dataUpdatedAt ? `Diperbarui ${relativeTime(new Date(q.dataUpdatedAt).toISOString(), now)} · otomatis 30 dtk` : "Belum ada data dimuat"}
            </span>
            <button type="button" data-testid="devices-refresh-button" onClick={() => void q.refetch()} disabled={q.isFetching} className="ctl ctl-ink h-9">
              <RefreshCw className={`h-4 w-4 ${q.isFetching ? "animate-spin" : ""}`} aria-hidden="true" /> Perbarui
            </button>
          </div>
        </div>

        <div className="glass rounded-card flex flex-wrap items-center gap-3 p-3">
          <StatusFilter value={filter} counts={counts} onChange={setFilter} />
          <label className="ctl relative w-full cursor-text pr-3 sm:ml-auto sm:w-64">
            <Search className="h-4 w-4 shrink-0 text-txt-2" aria-hidden="true" />
            <span className="sr-only">Cari perangkat atau toko</span>
            <input data-testid="devices-search-input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Cari perangkat / toko"
              className="w-full bg-transparent text-sm text-txt placeholder:text-txt-3 focus:outline-none" />
          </label>
        </div>

        {body()}

        <footer className="flex items-start gap-2 pt-2 text-xs text-txt-3">
          <Cpu className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          Status dihitung dari heartbeat (tiap 60 dtk; dianggap hilang setelah 3 mnt). Waktu ditampilkan dalam zona waktu toko masing-masing.
        </footer>
      </main>
    </AppShell>
  );
}
