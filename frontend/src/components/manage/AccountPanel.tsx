import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { api } from "../../api/client";
import { useAuth } from "../../hooks/useAuth";
import { errorMessage } from "../../hooks/useManageData";
import { Field, inputCls } from "./Modal";

export const AccountPanel = () => {
  const { session, memberships, isPlatformAdmin } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [pending, setPending] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next !== confirm) { toast.error("Konfirmasi sandi tidak sama"); return; }
    setPending(true);
    try {
      await api.changePassword(current, next);
      toast.success("Sandi diganti");
      setCurrent(""); setNext(""); setConfirm("");
    } catch (err) { toast.error(errorMessage(err)); } finally { setPending(false); }
  };
  return (
    <div data-testid="manage-account-panel" className="grid gap-4 lg:grid-cols-2">
      <section className="card p-5">
        <h3 className="text-sm font-semibold text-txt">Akun Anda</h3>
        <p data-testid="account-email" className="mt-1 text-sm text-txt-2">{session?.user.email}</p>
        <ul className="mt-4 space-y-1.5 text-xs text-txt-2" data-testid="account-roles">
          {isPlatformAdmin && <li className="font-medium text-txt">Platform admin — akses ke semua tenant</li>}
          {memberships.map((m) => <li key={m.tenant_id}><span className="font-medium text-txt">{m.tenant_name}</span> · {m.role === "owner" ? "Pemilik" : m.role === "staff" ? "Staf" : "Platform admin"}</li>)}
          {!isPlatformAdmin && memberships.length === 0 && <li>Belum memiliki akses ke tenant mana pun.</li>}
        </ul>
      </section>
      <form onSubmit={submit} className="card space-y-4 p-5">
        <h3 className="text-sm font-semibold text-txt">Ganti sandi</h3>
        <Field label="Sandi saat ini"><input required type="password" value={current} onChange={(e) => setCurrent(e.target.value)} className={inputCls} data-testid="account-current-password" autoComplete="current-password" /></Field>
        <Field label="Sandi baru" hint="Minimal 10 karakter"><input required type="password" minLength={10} value={next} onChange={(e) => setNext(e.target.value)} className={inputCls} data-testid="account-new-password" autoComplete="new-password" /></Field>
        <Field label="Ulangi sandi baru"><input required type="password" minLength={10} value={confirm} onChange={(e) => setConfirm(e.target.value)} className={inputCls} data-testid="account-confirm-password" autoComplete="new-password" /></Field>
        <div className="flex justify-end"><button type="submit" disabled={pending} className="ctl ctl-ink h-10" data-testid="account-change-password-submit">{pending ? "Menyimpan…" : "Ganti sandi"}</button></div>
      </form>
    </div>
  );
};
