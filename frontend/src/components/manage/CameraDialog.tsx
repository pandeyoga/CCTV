import { useState, type FormEvent } from "react";
import { api } from "../../api/client";
import type { CameraOut, DeviceOut } from "../../api/types";
import { useManageMutation } from "../../hooks/useManageData";
import { Field, FormActions, inputCls, Modal } from "./Modal";

interface Props {
  open: boolean;
  onClose: () => void;
  storeId: string;
  devices: DeviceOut[];
  camera?: CameraOut; // edit when set
}

export const CameraDialog = ({ open, onClose, storeId, devices, camera }: Props) => {
  const [externalId, setExternalId] = useState(camera?.external_id ?? "");
  const [name, setName] = useState(camera?.name ?? "");
  const [deviceId, setDeviceId] = useState(camera?.device_id ?? "");
  const m = useManageMutation(
    () => camera
      ? api.patchCamera(camera.camera_id, deviceId ? { name, device_id: deviceId } : { name, clear_device: true })
      : api.createCamera(storeId, { external_id: externalId, name, device_id: deviceId || null }),
    [["cameras", storeId]], camera ? "Kamera diperbarui" : "Kamera ditambahkan", onClose,
  );
  const submit = (e: FormEvent) => { e.preventDefault(); m.mutate(); };
  return (
    <Modal open={open} onClose={onClose} testId="camera-dialog" title={camera ? "Ubah kamera" : "Kamera baru"}
      description="camera_id harus sama persis dengan yang dikonfigurasi di edge agent (config.yaml).">
      <form onSubmit={submit} className="space-y-4">
        <Field label="camera_id (ID di edge)" hint="Huruf, angka, titik, garis bawah, strip. Tidak dapat diubah setelah dibuat.">
          <input required disabled={Boolean(camera)} pattern="[A-Za-z0-9_.-]+" maxLength={64} value={externalId} onChange={(e) => setExternalId(e.target.value)}
            className={`${inputCls} font-mono disabled:bg-surface-2 disabled:text-txt-3`} data-testid="camera-external-id-input" placeholder="cam-door-front" />
        </Field>
        <Field label="Nama tampilan">
          <input required maxLength={128} value={name} onChange={(e) => setName(e.target.value)} className={inputCls} data-testid="camera-name-input" placeholder="Pintu depan" />
        </Field>
        <Field label="Perangkat yang memproses" hint="Hanya perangkat ini yang boleh mengirim event untuk kamera ini. Kosong = perangkat mana pun di toko ini.">
          <select value={deviceId} onChange={(e) => setDeviceId(e.target.value)} className={inputCls} data-testid="camera-device-select">
            <option value="">— tidak ditentukan —</option>
            {devices.map((d) => <option key={d.device_id} value={d.device_id}>{d.name}{d.is_active ? "" : " (nonaktif)"}</option>)}
          </select>
        </Field>
        <FormActions onCancel={onClose} submitLabel={camera ? "Simpan" : "Tambah kamera"} pending={m.isPending} testId="camera-dialog" />
      </form>
    </Modal>
  );
};
