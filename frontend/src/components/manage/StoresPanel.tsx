import { useState } from "react";
import { Plus, Store } from "lucide-react";
import type { DeviceKeyOut, StoreOut, TenantOut } from "../../api/types";
import { useStores } from "../../hooks/useDashboardData";
import { KeyRevealDialog } from "./DeviceDialogs";
import { StoreCard } from "./StoreCard";
import { StoreDialog } from "./StoreDialog";

export const StoresPanel = ({ tenant, canManage }: { tenant: TenantOut; canManage: boolean }) => {
  const stores = useStores();
  const [create, setCreate] = useState(false);
  const [key, setKey] = useState<DeviceKeyOut | null>(null);
  const mine: StoreOut[] = (stores.data ?? []).filter((s) => s.tenant_id === tenant.tenant_id);
  return (
    <div data-testid="manage-stores-panel" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-txt-2">{mine.length} toko di <span className="font-medium text-txt">{tenant.name}</span>. Setiap toko memiliki perangkat edge dan kamera sendiri.</p>
        {canManage && <button type="button" onClick={() => setCreate(true)} className="ctl ctl-ink h-10" data-testid="manage-store-add"><Plus className="h-4 w-4" /> Toko baru</button>}
      </div>
      {stores.isPending && <div className="card h-40 animate-pulse" aria-hidden="true" />}
      {stores.data && mine.length === 0 && (
        <div data-testid="manage-stores-empty" className="card flex items-start gap-3 p-6">
          <span aria-hidden="true" className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-surface-2 text-txt-2"><Store className="h-4 w-4" /></span>
          <div>
            <p className="text-sm font-semibold text-txt">Belum ada toko</p>
            <p className="mt-1 text-xs text-txt-2">{canManage ? "Buat toko pertama, lalu tambahkan perangkat untuk mendapatkan API key edge agent." : "Minta pemilik tenant untuk menambahkan toko."}</p>
          </div>
        </div>
      )}
      {mine.map((s) => <StoreCard key={s.store_id} store={s} canManage={canManage} onKey={setKey} />)}
      {create && <StoreDialog open onClose={() => setCreate(false)} tenantId={tenant.tenant_id} />}
      <KeyRevealDialog out={key} onClose={() => setKey(null)} />
    </div>
  );
};
