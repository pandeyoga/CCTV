import { useState, type FormEvent } from "react";
import { Building2, Pencil, Plus, Power, UsersRound } from "lucide-react";
import { api } from "../../api/client";
import type { TenantOut } from "../../api/types";
import { useAuth } from "../../hooks/useAuth";
import { useManageMutation, useTenants, useUsers } from "../../hooks/useManageData";
import { Field, FormActions, inputCls, Modal } from "./Modal";

const TenantDialog = ({ tenant, onClose }: { tenant?: TenantOut; onClose: () => void }) => {
  const [name, setName] = useState(tenant?.name ?? "");
  const [email, setEmail] = useState(tenant?.contact_email ?? "");
  const body = { name, contact_email: email.trim() || null };
  const m = useManageMutation(() => (tenant ? api.patchTenant(tenant.tenant_id, body) : api.createTenant(body)),
    [["tenants"], ["users"]], tenant ? "Tenant diperbarui" : "Tenant dibuat", async () => { onClose(); });
  const submit = (e: FormEvent) => { e.preventDefault(); m.mutate(); };
  return (
    <Modal open onClose={onClose} testId="tenant-dialog" title={tenant ? "Ubah tenant" : "Tenant (pelanggan) baru"} description="Satu tenant = satu pelanggan yang memiliki satu atau beberapa toko.">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Nama tenant"><input required maxLength={128} value={name} onChange={(e) => setName(e.target.value)} className={inputCls} data-testid="tenant-name-input" placeholder="PT Ritel Nusantara" /></Field>
        <Field label="Email kontak (opsional)"><input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className={inputCls} data-testid="tenant-email-input" /></Field>
        <FormActions onCancel={onClose} submitLabel={tenant ? "Simpan" : "Buat tenant"} pending={m.isPending} testId="tenant-dialog" />
      </form>
    </Modal>
  );
};

export const TenantsPanel = ({ onOpenTenant }: { onOpenTenant: (id: string) => void }) => {
  const { refreshUser } = useAuth();
  const tenants = useTenants();
  const users = useUsers(true);
  const [dialog, setDialog] = useState<{ tenant?: TenantOut } | null>(null);
  const toggle = useManageMutation(({ id, active }: { id: string; active: boolean }) => api.patchUser(id, active), [["users"]], "Status pengguna diperbarui");
  return (
    <div data-testid="manage-tenants-panel" className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-txt-2">Anda platform admin: semua tenant dan pengguna terlihat di sini.</p>
        <button type="button" onClick={() => setDialog({})} className="ctl ctl-ink h-10" data-testid="tenant-add"><Plus className="h-4 w-4" /> Tenant baru</button>
      </div>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {tenants.data?.map((t) => (
          <li key={t.tenant_id} data-testid="tenant-card" className="card flex flex-col gap-3 p-4">
            <div className="flex items-start gap-3">
              <span aria-hidden="true" className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-ink text-white"><Building2 className="h-4 w-4" /></span>
              <div className="min-w-0 flex-1">
                <p data-testid="tenant-card-name" className="truncate text-sm font-semibold text-txt">{t.name}</p>
                <p className="truncate text-[11px] text-txt-3">{t.contact_email ?? "tanpa email kontak"} · {t.store_count} toko</p>
              </div>
              <button type="button" onClick={() => setDialog({ tenant: t })} aria-label="Ubah tenant" data-testid="tenant-edit" className="ctl ctl-ghost h-8 w-8 min-w-8 px-0 text-txt-2"><Pencil className="h-4 w-4" /></button>
            </div>
            <button type="button" onClick={() => onOpenTenant(t.tenant_id)} className="ctl h-9 text-xs" data-testid="tenant-open">Kelola toko & pengguna</button>
          </li>
        ))}
      </ul>

      <section className="card overflow-hidden">
        <header className="flex items-center gap-2 border-b border-line px-5 py-4"><UsersRound className="h-4 w-4 text-txt-2" /><h3 className="text-sm font-semibold text-txt">Semua pengguna ({users.data?.length ?? "…"})</h3></header>
        <ul className="divide-y divide-line" data-testid="users-list">
          {users.data?.map((u) => (
            <li key={u.user_id} data-testid="user-row" data-active={u.is_active} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-txt">{u.email}{u.is_platform_admin && <span className="ml-2 rounded-full bg-ink px-2 py-0.5 text-[10px] font-medium text-white">platform admin</span>}</p>
                <p className="truncate text-[11px] text-txt-3">{u.memberships.length ? u.memberships.map((m) => `${m.tenant_name} (${m.role === "owner" ? "pemilik" : "staf"})`).join(" · ") : u.is_platform_admin ? "semua tenant" : "tanpa akses tenant"}</p>
              </div>
              <span className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${u.is_active ? "bg-emerald-soft text-emerald-brand border-emerald-200" : "bg-surface-2 text-txt-2 border-line"}`}>{u.is_active ? "Aktif" : "Nonaktif"}</span>
              <button type="button" onClick={() => toggle.mutate({ id: u.user_id, active: !u.is_active })} aria-label={u.is_active ? "Nonaktifkan" : "Aktifkan"} title={u.is_active ? "Nonaktifkan" : "Aktifkan"} data-testid="user-toggle-active"
                className={`ctl ctl-ghost h-8 w-8 min-w-8 px-0 ${u.is_active ? "text-danger hover:bg-danger-soft" : "text-emerald-brand"}`}><Power className="h-4 w-4" /></button>
            </li>
          ))}
        </ul>
      </section>
      {dialog && <TenantDialog tenant={dialog.tenant} onClose={() => { setDialog(null); void refreshUser().catch(() => undefined); }} />}
    </div>
  );
};
