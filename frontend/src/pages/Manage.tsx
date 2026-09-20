import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Building2, KeyRound, Store, UsersRound } from "lucide-react";
import { AppShell } from "../components/dashboard/AppShell";
import { ErrorState } from "../components/dashboard/States";
import { AccountPanel } from "../components/manage/AccountPanel";
import { MembersPanel } from "../components/manage/MembersPanel";
import { StoresPanel } from "../components/manage/StoresPanel";
import { TenantsPanel } from "../components/manage/TenantsPanel";
import { useAuth } from "../hooks/useAuth";
import { useTenants } from "../hooks/useManageData";

type Tab = "stores" | "members" | "tenants" | "account";

export default function Manage() {
  const { isPlatformAdmin, canManage } = useAuth();
  const tenants = useTenants();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab | null) ?? "stores";
  const [tenantId, setTenantId] = useState<string | undefined>(params.get("tenant") ?? undefined);
  const tenant = useMemo(() => tenants.data?.find((t) => t.tenant_id === tenantId) ?? tenants.data?.[0], [tenants.data, tenantId]);
  useEffect(() => { if (tenant && tenant.tenant_id !== tenantId) setTenantId(tenant.tenant_id); }, [tenant, tenantId]);

  const setTab = (t: Tab) => setParams((p) => { p.set("tab", t); return p; }, { replace: true });
  const manageTenant = tenant ? canManage(tenant.tenant_id) : false;
  const TABS: { id: Tab; label: string; Icon: typeof Store; show: boolean }[] = [
    { id: "stores", label: "Toko & perangkat", Icon: Store, show: true },
    { id: "members", label: "Pengguna", Icon: UsersRound, show: manageTenant },
    { id: "tenants", label: "Tenant", Icon: Building2, show: isPlatformAdmin },
    { id: "account", label: "Akun", Icon: KeyRound, show: true },
  ];
  const active = TABS.find((t) => t.id === tab && t.show)?.id ?? "stores";

  const body = () => {
    if (active === "account") return <AccountPanel />;
    if (active === "tenants") return <TenantsPanel onOpenTenant={(id) => { setTenantId(id); setTab("stores"); }} />;
    if (tenants.isPending) return <div className="card h-40 animate-pulse" aria-hidden="true" />;
    if (!tenants.data) return <ErrorState message={(tenants.error as Error).message} onRetry={() => void tenants.refetch()} />;
    if (!tenant) return <div data-testid="manage-no-tenant" className="card p-6 text-sm text-txt-2">Anda belum memiliki akses ke tenant mana pun. {isPlatformAdmin ? "Buat tenant pada tab Tenant." : "Hubungi pemilik tenant atau operator."}</div>;
    return active === "members" ? <MembersPanel tenant={tenant} /> : <StoresPanel tenant={tenant} canManage={manageTenant} />;
  };

  return (
    <AppShell>
      <main data-testid="manage-page" className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-txt">Pengaturan</h1>
            <p className="mt-1 text-sm text-txt-2">Kelola toko, perangkat edge, kamera dan pengguna tanpa bantuan operator.</p>
          </div>
          {(tenants.data?.length ?? 0) > 1 && active !== "tenants" && active !== "account" && (
            <label className="ctl h-10 gap-2 pr-2 text-xs">
              <Building2 className="h-4 w-4 text-txt-2" aria-hidden="true" />
              <span className="sr-only">Tenant</span>
              <select value={tenant?.tenant_id ?? ""} onChange={(e) => setTenantId(e.target.value)} className="bg-transparent text-sm font-medium text-txt focus:outline-none" data-testid="manage-tenant-select">
                {tenants.data!.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.name}</option>)}
              </select>
            </label>
          )}
        </div>

        <nav aria-label="Bagian pengaturan" className="glass rounded-card flex flex-wrap gap-1 p-1.5" data-testid="manage-tabs">
          {TABS.filter((t) => t.show).map((t) => (
            <button key={t.id} type="button" onClick={() => setTab(t.id)} aria-current={active === t.id ? "page" : undefined} data-testid={`manage-tab-${t.id}`}
              className={`ctl h-10 border-transparent shadow-none ${active === t.id ? "ctl-ink" : "ctl-ghost text-txt-2"}`}>
              <t.Icon className="h-4 w-4" aria-hidden="true" /> {t.label}
            </button>
          ))}
        </nav>

        {body()}
      </main>
    </AppShell>
  );
}
