import { useState, type FormEvent } from "react";
import { Check, Copy, KeyRound } from "lucide-react";
import { api } from "../../api/client";
import type { DeviceKeyOut, DeviceOut } from "../../api/types";
import { useManageMutation } from "../../hooks/useManageData";
import { Field, FormActions, inputCls, Modal } from "./Modal";

/** Shown exactly once after create / rotate. The server never returns the key again. */
export const KeyRevealDialog = ({ out, onClose }: { out: DeviceKeyOut | null; onClose: () => void }) => {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(out!.api_key_show_once); setCopied(true); } catch { setCopied(false); }
  };
  return (
    <Modal open={out !== null} onClose={onClose} testId="key-reveal-dialog" title={`API key perangkat ${out?.device.name ?? ""}`}
      description="Simpan sekarang. Kunci ini hanya ditampilkan sekali dan tidak dapat dilihat lagi; jika hilang, lakukan rotasi kunci.">
      {out && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 rounded-ctl border border-line bg-surface-2 p-3">
            <KeyRound className="h-4 w-4 shrink-0 text-emerald-brand" aria-hidden="true" />
            <code data-testid="device-api-key" className="font-mono min-w-0 flex-1 break-all text-xs text-txt">{out.api_key_show_once}</code>
            <button type="button" onClick={copy} data-testid="device-api-key-copy" className="ctl h-9 shrink-0">
              {copied ? <Check className="h-4 w-4 text-emerald-brand" /> : <Copy className="h-4 w-4" />} {copied ? "Tersalin" : "Salin"}
            </button>
          </div>
          <p className="text-xs text-txt-2">
            Di edge device, set variabel lingkungan <code className="font-mono rounded bg-surface-2 px-1">EDGE_API_KEY</code> dengan nilai ini, lalu restart agent.
          </p>
          <div className="flex justify-end">
            <button type="button" onClick={onClose} className="ctl ctl-ink h-10" data-testid="key-reveal-done">Sudah saya simpan</button>
          </div>
        </div>
      )}
    </Modal>
  );
};

interface DeviceDialogProps {
  open: boolean;
  onClose: () => void;
  storeId: string;
  device?: DeviceOut; // rename when set
  onCreated: (out: DeviceKeyOut) => void;
}

export const DeviceDialog = ({ open, onClose, storeId, device, onCreated }: DeviceDialogProps) => {
  const [name, setName] = useState(device?.name ?? "");
  const m = useManageMutation<DeviceKeyOut | DeviceOut>(
    () => (device ? api.patchDevice(device.device_id, { name }) : api.createDevice(storeId, name)),
    [["devices"]], device ? "Perangkat diperbarui" : "Perangkat dibuat",
    (out) => { onClose(); if (!device) onCreated(out as DeviceKeyOut); },
  );
  const submit = (e: FormEvent) => { e.preventDefault(); m.mutate(); };
  return (
    <Modal open={open} onClose={onClose} testId="device-dialog" title={device ? "Ubah nama perangkat" : "Perangkat (edge) baru"}
      description={device ? undefined : "Setelah dibuat, API key perangkat ditampilkan satu kali."}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="Nama perangkat" hint="Contoh: edge-pintu-depan">
          <input required maxLength={128} value={name} onChange={(e) => setName(e.target.value)} className={inputCls} data-testid="device-name-input" />
        </Field>
        <FormActions onCancel={onClose} submitLabel={device ? "Simpan" : "Buat & tampilkan key"} pending={m.isPending} testId="device-dialog" />
      </form>
    </Modal>
  );
};
