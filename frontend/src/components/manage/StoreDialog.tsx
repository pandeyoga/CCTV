import { useState, type FormEvent } from "react";
import { api } from "../../api/client";
import type { StoreOut } from "../../api/types";
import { useManageMutation } from "../../hooks/useManageData";
import { Field, FormActions, inputCls, Modal } from "./Modal";

export const TIMEZONES = ["Asia/Jakarta", "Asia/Makassar", "Asia/Jayapura", "Asia/Singapore", "Asia/Kuala_Lumpur", "UTC"];

interface Props {
  open: boolean;
  onClose: () => void;
  tenantId: string;
  store?: StoreOut; // edit when set
}

export const StoreDialog = ({ open, onClose, tenantId, store }: Props) => {
  const [name, setName] = useState(store?.name ?? "");
  const [tz, setTz] = useState(store?.timezone ?? "Asia/Jakarta");
  const [custom, setCustom] = useState(store ? !TIMEZONES.includes(store.timezone) : false);
  const [allDay, setAllDay] = useState(!store?.open_time);
  const [openT, setOpenT] = useState(store?.open_time ?? "09:00");
  const [closeT, setCloseT] = useState(store?.close_time ?? "21:00");
  const hours = allDay ? { open_time: null, close_time: null } : { open_time: openT, close_time: closeT };
  const overnight = !allDay && closeT <= openT;
  const m = useManageMutation(
    () => (store ? api.patchStore(store.store_id, { name, timezone: tz, ...hours }) : api.createStore({ tenant_id: tenantId, name, timezone: tz, ...hours })),
    [["stores"], ["tenants"], ["overview"], ["report"]], store ? "Toko diperbarui" : "Toko dibuat", onClose,
  );
  const submit = (e: FormEvent) => { e.preventDefault(); m.mutate(); };
  return (
    <Modal open={open} onClose={onClose} testId="store-dialog" title={store ? "Ubah toko" : "Toko baru"}
      description="Zona waktu menentukan hari dan jam pada laporan; jam operasional menentukan event mana yang dihitung.">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Nama toko">
          <input required maxLength={128} value={name} onChange={(e) => setName(e.target.value)} className={inputCls} data-testid="store-name-input" placeholder="Toko Pusat" />
        </Field>
        <Field label="Zona waktu (IANA)">
          {custom
            ? <input required value={tz} onChange={(e) => setTz(e.target.value)} className={inputCls} data-testid="store-timezone-input" placeholder="Asia/Jakarta" />
            : <select value={tz} onChange={(e) => (e.target.value === "__custom" ? (setCustom(true), setTz("")) : setTz(e.target.value))} className={inputCls} data-testid="store-timezone-select">
                {TIMEZONES.map((z) => <option key={z} value={z}>{z}</option>)}
                <option value="__custom">Lainnya…</option>
              </select>}
        </Field>
        <fieldset className="space-y-2">
          <legend className="mb-1.5 block text-xs font-medium text-txt-2">Jam operasional</legend>
          <label className="flex items-center gap-2 text-sm text-txt">
            <input type="checkbox" checked={allDay} onChange={(e) => setAllDay(e.target.checked)} data-testid="store-all-day-checkbox" className="h-4 w-4 accent-emerald-700" />
            Buka 24 jam (semua event dihitung)
          </label>
          {!allDay && (
            <div className="flex flex-wrap items-center gap-2 text-sm text-txt-2">
              <input type="time" required value={openT} onChange={(e) => setOpenT(e.target.value)} className={`${inputCls} w-32`} data-testid="store-open-input" aria-label="Buka" />
              <span>s.d.</span>
              <input type="time" required value={closeT} onChange={(e) => setCloseT(e.target.value)} className={`${inputCls} w-32`} data-testid="store-close-input" aria-label="Tutup" />
            </div>
          )}
          <p className="text-[11px] text-txt-3">
            {allDay ? "Laporan dan status perangkat memakai seluruh hari." : overnight ? "Jam tutup lebih awal dari jam buka → dianggap buka melewati tengah malam." : "Event di luar jam ini tidak dihitung dan perangkat tidak dianggap bermasalah saat toko tutup."}
          </p>
        </fieldset>
        <FormActions onCancel={onClose} submitLabel={store ? "Simpan" : "Buat toko"} pending={m.isPending} testId="store-dialog" />
      </form>
    </Modal>
  );
};
