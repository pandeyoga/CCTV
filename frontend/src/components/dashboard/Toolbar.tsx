import { CalendarDays, ChevronDown, ChevronLeft, ChevronRight, RefreshCw, Store } from "lucide-react";
import type { StoreOut } from "../../api/types";

interface Props {
  stores: StoreOut[];
  store: StoreOut | undefined;
  onStoreChange: (id: string) => void;
  date: string;
  today: string;
  onDateChange: (d: string) => void;
  onPrev: () => void;
  onNext: () => void;
  isFetching: boolean;
  onRefresh: () => void;
}

export const Toolbar = (p: Props) => (
  <div data-testid="dashboard-toolbar" className="glass rounded-card p-3 flex flex-wrap items-center gap-2">
    <label className="ctl relative w-full sm:w-auto sm:flex-1 sm:max-w-xs cursor-pointer pr-9">
      <Store className="h-4 w-4 shrink-0 text-txt-2" aria-hidden="true" />
      <span className="sr-only">Pilih toko</span>
      <select data-testid="store-selector-dropdown" value={p.store?.store_id ?? ""} disabled={p.stores.length === 0}
        onChange={(e) => p.onStoreChange(e.target.value)}
        className="w-full appearance-none truncate bg-transparent text-sm font-semibold text-txt focus:outline-none disabled:cursor-not-allowed">
        {p.stores.length === 0 && <option value="">Tidak ada toko</option>}
        {p.stores.map((s) => <option key={s.store_id} value={s.store_id}>{s.name}</option>)}
      </select>
      <ChevronDown className="pointer-events-none absolute right-3 h-4 w-4 text-txt-3" aria-hidden="true" />
    </label>

    <div role="group" aria-label="Pilih tanggal" className="ctl p-1 gap-0 w-full sm:w-auto justify-between">
      <button type="button" data-testid="date-prev-button" onClick={p.onPrev} aria-label="Hari sebelumnya"
        className="ctl ctl-ghost h-9 min-w-9 px-2 hover:bg-surface-2">
        <ChevronLeft className="h-4 w-4" aria-hidden="true" />
      </button>
      <label className="flex items-center gap-2 px-2 cursor-pointer">
        <CalendarDays className="h-4 w-4 text-emerald-brand" aria-hidden="true" />
        <span className="sr-only">Tanggal</span>
        <input data-testid="date-picker-trigger" type="date" value={p.date} max={p.today}
          onChange={(e) => e.target.value && p.onDateChange(e.target.value)}
          className="bg-transparent text-sm font-medium tnum text-txt focus:outline-none" />
      </label>
      <button type="button" data-testid="date-next-button" onClick={p.onNext} disabled={p.date >= p.today} aria-label="Hari berikutnya"
        className="ctl ctl-ghost h-9 min-w-9 px-2 hover:bg-surface-2 disabled:bg-transparent">
        <ChevronRight className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>

    <div className="flex w-full sm:w-auto sm:ml-auto items-center justify-end gap-2">
      <button type="button" data-testid="date-today-button" onClick={() => p.onDateChange(p.today)}
        aria-pressed={p.date === p.today} className={`ctl ${p.date === p.today ? "ctl-ink" : ""}`}>
        Hari ini
      </button>
      <button type="button" data-testid="manual-refresh-button" onClick={p.onRefresh} disabled={p.isFetching}
        className="ctl ctl-ink">
        <RefreshCw className={`h-4 w-4 ${p.isFetching ? "animate-spin" : ""}`} aria-hidden="true" />
        <span>Perbarui</span>
      </button>
    </div>
  </div>
);
