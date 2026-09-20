import { useState, type FormEvent } from "react";
import { RotateCcw } from "lucide-react";
import { api } from "../../api/client";
import type { AlertRulesOut } from "../../api/types";
import { useManageMutation } from "../../hooks/useManageData";
import { Field, FormActions, inputCls, Modal } from "./Modal";

interface Props {
  open: boolean;
  onClose: () => void;
  storeId: string;
  storeName: string;
  rules: AlertRulesOut;
}

const num = (v: string) => Number.parseInt(v, 10);

export const AlertRulesDialog = ({ open, onClose, storeId, storeName, rules }: Props) => {
  const [hb, setHb] = useState(String(rules.heartbeat_lost_min));
  const [cam, setCam] = useState(String(rules.camera_down_min));
  const [buf, setBuf] = useState(String(rules.buffer_pending_threshold));
  const [noEv, setNoEv] = useState(rules.no_events_min !== null);
  const [noEvMin, setNoEvMin] = useState(String(rules.no_events_min ?? 60));
  const keys = [["alert-rules", storeId], ["alerts"]];
  const save = useManageMutation(
    () => api.putAlertRules(storeId, { heartbeat_lost_min: num(hb), camera_down_min: num(cam), buffer_pending_threshold: num(buf), no_events_min: noEv ? num(noEvMin) : null }),
    keys, "Aturan alert disimpan", onClose,
  );
  const reset = useManageMutation(() => api.resetAlertRules(storeId), keys, "Aturan alert dikembalikan ke bawaan", onClose);
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(); };
  return (
    <Modal open={open} onClose={onClose} testId="alert-rules-dialog" title={`Aturan alert · ${storeName}`}
      description="Alert dibuat hanya pada jam operasional toko dan otomatis selesai saat kondisinya pulih.">
      <form onSubmit={submit} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Tanpa heartbeat lebih dari (menit)" hint="Heartbeat dikirim tiap 60 dtk; bawaan 3.">
            <input type="number" required min={1} max={1440} value={hb} onChange={(e) => setHb(e.target.value)} className={inputCls} data-testid="alert-rules-heartbeat-input" />
          </Field>
          <Field label="Kamera terputus lebih dari (menit)" hint="Bawaan 2.">
            <input type="number" required min={1} max={1440} value={cam} onChange={(e) => setCam(e.target.value)} className={inputCls} data-testid="alert-rules-camera-input" />
          </Field>
          <Field label="Buffer penuh: event tertunda ≥" hint="Bawaan 1000.">
            <input type="number" required min={1} max={1000000} value={buf} onChange={(e) => setBuf(e.target.value)} className={inputCls} data-testid="alert-rules-buffer-input" />
          </Field>
          <fieldset className="space-y-2">
            <legend className="mb-1.5 block text-xs font-medium text-txt-2">Tidak ada event pada jam buka</legend>
            <label className="flex items-center gap-2 text-sm text-txt">
              <input type="checkbox" checked={noEv} onChange={(e) => setNoEv(e.target.checked)} data-testid="alert-rules-no-events-checkbox" className="h-4 w-4 accent-emerald-700" />
              Aktifkan
            </label>
            {noEv && (
              <input type="number" required min={5} max={1440} value={noEvMin} onChange={(e) => setNoEvMin(e.target.value)} className={inputCls} aria-label="menit tanpa event" data-testid="alert-rules-no-events-input" />
            )}
            <p className="text-[11px] text-txt-3">{noEv ? "Menit tanpa event masuk/keluar (min. 5; bawaan 60). Hanya saat ada perangkat terhubung dan kamera terdaftar." : "Aturan dimatikan untuk toko ini."}</p>
          </fieldset>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <button type="button" onClick={() => reset.mutate()} disabled={rules.is_default || reset.isPending} data-testid="alert-rules-reset" className="ctl ctl-ghost h-9 text-txt-2 disabled:opacity-50">
            <RotateCcw className="h-4 w-4" aria-hidden="true" /> Kembalikan bawaan
          </button>
          <span className="text-[11px] text-txt-3" data-testid="alert-rules-state">{rules.is_default ? "Memakai nilai bawaan" : "Disesuaikan untuk toko ini"}</span>
        </div>
        <FormActions onCancel={onClose} submitLabel="Simpan" pending={save.isPending} testId="alert-rules-dialog" />
      </form>
    </Modal>
  );
};
