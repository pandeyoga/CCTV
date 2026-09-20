import { useState, type FormEvent } from "react";
import { KeyRound, Plus, ShieldCheck, Trash2, UserRound } from "lucide-react";
import { api } from "../../api/client";
import type { MemberOut, TenantOut } from "../../api/types";
import { useAuth } from "../../hooks/useAuth";
import { useManageMutation, useMembers } from "../../hooks/useManageData";
import { Field, FormActions, inputCls, Modal } from "./Modal";

const ROLE_LABEL = { owner: "Pemilik (kelola)", staff: "Staf (lihat saja)" } as const;

const MemberDialog = ({ tenantId, onClose }: { tenantId: string; onClose: () => void }) => {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"owner" | "staff">("staff");
  const [password, setPassword] = useState("");
  const m = useManageMutation(() => api.addMember(tenantId, { email: email.trim().toLowerCase(), role, ...(password ? { password } : {}) }),
    [["members", tenantId], ["users"]], "Pengguna ditambahkan", onClose);
  const submit = (e: FormEvent) => { e.preventDefault(); m.mutate(); };
  return (
    <Modal open onClose={onClose} testId="member-dialog" title="Tambah pengguna" description="Pengguna baru dibuat dengan sandi awal; pengguna yang sudah ada cukup diberi akses.">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Email"><input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} className={inputCls} data-testid="member-email-input" placeholder="nama@toko.id" /></Field>
        <Field label="Peran">
          <select value={role} onChange={(e) => setRole(e.target.value as "owner" | "staff")} className={inputCls} data-testid="member-role-select">
            <option value="staff">{ROLE_LABEL.staff}</option>
            <option value="owner">{ROLE_LABEL.owner}</option>
          </select>
        </Field>
        <Field label="Sandi awal" hint="Wajib untuk pengguna baru (minimal 10 karakter). Kosongkan jika email sudah terdaftar.">
          <input type="password" minLength={10} maxLength={256} value={password} onChange={(e) => setPassword(e.target.value)} className={inputCls} data-testid="member-password-input" autoComplete="new-password" />
        </Field>
        <FormActions onCancel={onClose} submitLabel="Tambah" pending={m.isPending} testId="member-dialog" />
      </form>
    </Modal>
  );
};

const ResetDialog = ({ member, onClose }: { member: MemberOut; onClose: () => void }) => {
  const [password, setPassword] = useState("");
  const m = useManageMutation(() => api.resetPassword(member.user_id, password), [], `Sandi ${member.email} diganti`, onClose);
  const submit = (e: FormEvent) => { e.preventDefault(); m.mutate(); };
  return (
    <Modal open onClose={onClose} testId="reset-dialog" title={`Reset sandi ${member.email}`} description="Sandi lama langsung tidak berlaku. Sampaikan sandi baru secara aman.">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Sandi baru" hint="Minimal 10 karakter">
          <input required type="password" minLength={10} maxLength={256} value={password} onChange={(e) => setPassword(e.target.value)} className={inputCls} data-testid="reset-password-input" autoComplete="new-password" />
        </Field>
        <FormActions onCancel={onClose} submitLabel="Ganti sandi" pending={m.isPending} testId="reset-dialog" />
      </form>
    </Modal>
  );
};

const MemberRow = ({ m, tenantId }: { m: MemberOut; tenantId: string }) => {
  const { session } = useAuth();
  const self = session?.user.user_id === m.user_id;
  const [reset, setReset] = useState(false);
  const role = useManageMutation((r: "owner" | "staff") => api.patchMember(tenantId, m.user_id, r), [["members", tenantId], ["users"]], "Peran diperbarui");
  const remove = useManageMutation(() => api.removeMember(tenantId, m.user_id), [["members", tenantId], ["users"]], "Akses dicabut");
  return (
    <li data-testid="member-row" data-role={m.role} className="flex flex-wrap items-center gap-3 px-4 py-3">
      <span aria-hidden="true" className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg border ${m.role === "owner" ? "bg-emerald-soft text-emerald-brand border-emerald-200" : "bg-surface-2 text-txt-2 border-line"}`}>
        {m.role === "owner" ? <ShieldCheck className="h-4 w-4" /> : <UserRound className="h-4 w-4" />}
      </span>
      <div className="min-w-0 flex-1">
        <p data-testid="member-email" className="truncate text-sm font-medium text-txt">{m.email}{self && <span className="ml-2 text-[11px] font-normal text-txt-3">(Anda)</span>}</p>
        <p className="text-[11px] text-txt-3">{m.is_active ? ROLE_LABEL[m.role] : "Akun dinonaktifkan"}</p>
      </div>
      <select value={m.role} disabled={self || role.isPending} onChange={(e) => role.mutate(e.target.value as "owner" | "staff")}
        className="ctl h-9 pr-8 text-xs disabled:opacity-60" data-testid="member-role-change" aria-label={`Peran ${m.email}`}>
        <option value="staff">Staf</option>
        <option value="owner">Pemilik</option>
      </select>
      <button type="button" onClick={() => setReset(true)} disabled={self} title="Reset sandi" aria-label="Reset sandi" data-testid="member-reset-password" className="ctl ctl-ghost h-8 w-8 min-w-8 px-0 text-txt-2 disabled:opacity-40"><KeyRound className="h-4 w-4" /></button>
      <button type="button" onClick={() => window.confirm(`Cabut akses ${m.email} dari tenant ini?`) && remove.mutate()} disabled={self} title="Cabut akses" aria-label="Cabut akses" data-testid="member-remove" className="ctl ctl-ghost h-8 w-8 min-w-8 px-0 text-danger hover:bg-danger-soft disabled:opacity-40"><Trash2 className="h-4 w-4" /></button>
      {reset && <ResetDialog member={m} onClose={() => setReset(false)} />}
    </li>
  );
};

export const MembersPanel = ({ tenant }: { tenant: TenantOut }) => {
  const q = useMembers(tenant.tenant_id);
  const [add, setAdd] = useState(false);
  return (
    <div data-testid="manage-members-panel" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-txt-2"><span className="font-medium text-txt">Pemilik</span> mengelola toko, perangkat dan pengguna; <span className="font-medium text-txt">Staf</span> hanya melihat ringkasan dan perangkat.</p>
        <button type="button" onClick={() => setAdd(true)} className="ctl ctl-ink h-10" data-testid="member-add"><Plus className="h-4 w-4" /> Tambah pengguna</button>
      </div>
      {q.isPending && <div className="card h-32 animate-pulse" aria-hidden="true" />}
      {q.isError && <p className="card p-4 text-sm text-danger">{(q.error as Error).message}</p>}
      {q.data && <ul className="card divide-y divide-line overflow-hidden">{q.data.map((m) => <MemberRow key={m.user_id} m={m} tenantId={tenant.tenant_id} />)}</ul>}
      {add && <MemberDialog tenantId={tenant.tenant_id} onClose={() => setAdd(false)} />}
    </div>
  );
};
