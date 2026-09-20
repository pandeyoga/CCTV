import { Loader2 } from "lucide-react";
import type { StoreOut } from "../../api/types";
import { formatDateLong, relativeTime } from "../../lib/time";

interface Props {
  store: StoreOut | undefined;
  storesFailed: boolean;
  date: string;
  updatedAt: number | null;
  isRefreshing: boolean;
  now: Date;
}

export const PageHeader = ({ store, storesFailed, date, updatedAt, isRefreshing, now }: Props) => (
  <div data-testid="dashboard-header" className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
    <div className="min-w-0">
      <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-txt">Ringkasan pengunjung</h1>
      <p data-testid="selected-date-label" className="mt-1 text-sm text-txt-2">
        {store
          ? <><span className="font-medium text-txt">{store.name}</span> · {formatDateLong(date)}</>
          : storesFailed ? "Daftar toko tidak dapat dimuat" : "Memuat daftar toko…"}
      </p>
    </div>
    <div className="flex flex-wrap items-center gap-2 text-xs text-txt-2">
      {store && (
        <span data-testid="timezone-badge" className="rounded-full border border-line bg-surface px-2.5 py-1 font-medium">
          Zona waktu {store.timezone}
        </span>
      )}
      <span data-testid="last-updated-time" className="rounded-full border border-line bg-surface px-2.5 py-1">
        {updatedAt ? `Diperbarui ${relativeTime(new Date(updatedAt).toISOString(), now)} · otomatis 30 dtk` : "Belum ada data dimuat"}
      </span>
      {isRefreshing && (
        <span data-testid="refreshing-indicator" role="status" className="inline-flex items-center gap-1.5 rounded-full bg-emerald-soft px-2.5 py-1 font-medium text-emerald-brand">
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> Memperbarui…
        </span>
      )}
    </div>
  </div>
);
