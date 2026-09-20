import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Bell, BellOff, CheckCheck, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { api } from "../api/client";
import { AppShell } from "../components/dashboard/AppShell";
import { ErrorState, StaleBanner } from "../components/dashboard/States";
import { AlertRow } from "../components/alerts/AlertRow";
import { useAlerts, type AlertStatusFilter } from "../hooks/useAlerts";
import { useAuth } from "../hooks/useAuth";
import { useManageMutation, errorMessage } from "../hooks/useManageData";
import { useNow } from "../hooks/useNow";
import { useStores } from "../hooks/useDashboardData";
import { relativeTime } from "../lib/time";

const TABS: { id: AlertStatusFilter; label: string }[] = [
  { id: "open", label: "Aktif" },
  { id: "resolved", label: "Riwayat" },
  { id: "all", label: "Semua" },
];

const Bone = ({ className }: { className: string }) => <div aria-hidden="true" className={`animate-pulse rounded-lg bg-zinc-200/80 ${className}`} />;

export default function Alerts() {
  const now = useNow();
  const qc = useQueryClient();
  const { canManage } = useAuth();
  const [tab, setTab] = useState<AlertStatusFilter>("open");
  const [storeId, setStoreId] = useState<string>("");
  const stores = useStores();
  const q = useAlerts(tab, storeId || undefined);
  const ack = useManageMutation((id: string) => api.ackAlert(id), [["alerts"]], "");
  const ackAll = async () => {
    const pending = (q.data?.alerts ?? []).filter((a) => a.resolved_at === null && !a.acknowledged_at && canManage(a.tenant_id));
    const results = await Promise.allSettled(pending.map((a) => api.ackAlert(a.alert_id)));
    await qc.invalidateQueries({ queryKey: ["alerts"] });
    const failed = results.filter((r) => r.status === "rejected");
    if (failed.length === 0) toast.success(`${pending.length} alert ditandai dilihat`);
    else toast.error(`${failed.length} dari ${pending.length} alert gagal ditandai: ${errorMessage((failed[0] as PromiseRejectedResult).reason)}`);
  };
  const unacked = useMemo(() => (q.data?.alerts ?? []).filter((a) => a.resolved_at === null && !a.acknowledged_at && canManage(a.tenant_id)).length, [q.data, canManage]);

  const body = () => {
    if (q.isPending) return (
      <div data-testid="alerts-skeleton" role="status" aria-label="Memuat alert" className="card divide-y divide-line">
        {[0, 1, 2].map((i) => <div key={i} className="flex items-center gap-4 p-4"><Bone className="h-9 w-9 rounded-xl" /><div className="flex-1 space-y-2"><Bone className="h-4 w-48" /><Bone className="h-3 w-72" /></div></div>)}
      </div>
    );
    if (!q.data) return <ErrorState message={(q.error as Error).message} onRetry={() => void q.refetch()} />;
    const rows = q.data.alerts;
    return (
      <>
        {q.isError && <StaleBanner message={(q.error as Error).message} onRetry={() => void q.refetch()} />}
        {rows.length === 0 && (
          <div data-testid="alerts-empty" className="card flex items-start gap-3 p-6">
            <span aria-hidden="true" className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-emerald-soft text-emerald-brand"><BellOff className="h-4 w-4" /></span>
            <div>
              <p className="text-sm font-semibold text-txt">{tab === "open" ? "Tidak ada alert aktif" : "Belum ada riwayat alert"}</p>
              <p className="text-xs text-txt-2">{tab === "open" ? "Semua perangkat melapor normal pada jam operasional toko yang dapat Anda akses." : "Alert yang sudah selesai akan tercatat di sini."}</p>
            </div>
          </div>
        )}
        {rows.length > 0 && (
          <ul data-testid="alerts-list" className="card divide-y divide-line overflow-hidden">
            {rows.map((a) => <AlertRow key={a.alert_id} a={a} now={now} canAck={canManage(a.tenant_id)} onAck={(id) => ack.mutate(id)} acking={ack.isPending} />)}
          </ul>
        )}
      </>
    );
  };

  return (
    <AppShell>
      <main data-testid="alerts-page" className="mx-auto max-w-5xl space-y-6 p-4 sm:p-6 lg:p-8">
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-txt">Notifikasi</h1>
            <p className="mt-1 text-sm text-txt-2">Alert kesehatan operasional: heartbeat hilang, kamera terputus, buffer penuh, dan toko tanpa event pada jam buka.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-txt-2">
            <span data-testid="alerts-updated" className="rounded-full border border-line bg-surface px-2.5 py-1">
              {q.data ? `Dievaluasi ${relativeTime(q.data.evaluated_at, now)} · otomatis 30 dtk` : "Belum ada data dimuat"}
            </span>
            <button type="button" data-testid="alerts-refresh-button" onClick={() => void q.refetch()} disabled={q.isFetching} className="ctl ctl-ink h-9">
              <RefreshCw className={`h-4 w-4 ${q.isFetching ? "animate-spin" : ""}`} aria-hidden="true" /> Perbarui
            </button>
          </div>
        </div>

        <div className="glass rounded-card flex flex-wrap items-center gap-3 p-3">
          <div role="tablist" aria-label="Status alert" className="flex flex-wrap gap-1.5">
            {TABS.map((t) => (
              <button key={t.id} role="tab" type="button" aria-selected={tab === t.id} onClick={() => setTab(t.id)} data-testid={`alerts-tab-${t.id}`}
                className={`ctl h-9 ${tab === t.id ? "ctl-ink" : ""}`}>
                {t.label}
                {t.id === "open" && q.data && <span data-testid="alerts-open-count" className={`ml-1 rounded-full px-1.5 text-[11px] tnum ${tab === "open" ? "bg-white/15" : "bg-surface-2"}`}>{q.data.open_count}</span>}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2 sm:ml-auto">
            <select value={storeId} onChange={(e) => setStoreId(e.target.value)} aria-label="Filter toko" data-testid="alerts-store-select" className="ctl h-9 pr-8 text-sm">
              <option value="">Semua toko</option>
              {stores.data?.map((s) => <option key={s.store_id} value={s.store_id}>{s.name}</option>)}
            </select>
            {unacked > 0 && (
              <button type="button" onClick={() => void ackAll()} data-testid="alerts-ack-all" className="ctl h-9"><CheckCheck className="h-4 w-4" aria-hidden="true" /> Tandai semua dilihat ({unacked})</button>
            )}
          </div>
        </div>

        {body()}

        <footer className="flex items-start gap-2 pt-2 text-xs text-txt-3">
          <Bell className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          Aturan per toko diatur di Pengaturan → Toko → Aturan alert. Alert hanya dibuat pada jam operasional toko dan selesai otomatis saat kondisinya pulih. Kanal email/WhatsApp belum tersedia.
        </footer>
      </main>
    </AppShell>
  );
}
