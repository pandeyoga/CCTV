import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bell, Camera, Cpu, KeyRound, Pencil, Plus, Power, Trash2 } from "lucide-react";
import { api } from "../../api/client";
import type { CameraOut, DeviceKeyOut, DeviceOut, StoreOut } from "../../api/types";
import { useAlertRules } from "../../hooks/useAlerts";
import { useCameras, useManageMutation } from "../../hooks/useManageData";
import { useNow } from "../../hooks/useNow";
import { DEVICE_STATUS, statusOf } from "../../lib/deviceStatus";
import { relativeTime } from "../../lib/time";
import { AlertRulesDialog } from "./AlertRulesDialog";
import { CameraDialog } from "./CameraDialog";
import { DeviceDialog } from "./DeviceDialogs";
import { StoreDialog } from "./StoreDialog";

interface Props {
  store: StoreOut;
  canManage: boolean;
  onKey: (out: DeviceKeyOut) => void;
}

const IconBtn = ({ onClick, label, testId, children, danger = false }: { onClick: () => void; label: string; testId: string; children: React.ReactNode; danger?: boolean }) => (
  <button type="button" onClick={onClick} aria-label={label} title={label} data-testid={testId}
    className={`ctl ctl-ghost h-8 w-8 min-w-8 px-0 ${danger ? "text-danger hover:bg-danger-soft" : "text-txt-2"}`}>{children}</button>
);

const DeviceLine = ({ d, storeId, canManage, onKey }: { d: DeviceOut; storeId: string; canManage: boolean; onKey: (o: DeviceKeyOut) => void }) => {
  const now = useNow();
  const st = statusOf(d, now);
  const { label, cls, Icon } = DEVICE_STATUS[st];
  const [rename, setRename] = useState(false);
  const toggle = useManageMutation(() => api.patchDevice(d.device_id, { is_active: !d.is_active }), [["devices"]], d.is_active ? "Perangkat dinonaktifkan" : "Perangkat diaktifkan");
  const rotate = useManageMutation(() => api.rotateDeviceKey(d.device_id), [["devices"]], "Kunci baru dibuat; kunci lama tidak berlaku lagi", (o) => onKey(o as DeviceKeyOut));
  const confirmRotate = () => {
    if (window.confirm(`Rotasi kunci ${d.name}? Kunci lama langsung berhenti bekerja dan edge agent harus diperbarui.`)) rotate.mutate();
  };
  return (
    <li data-testid="manage-device-row" data-status={st} className="flex flex-wrap items-center gap-3 px-4 py-3">
      <span aria-hidden="true" className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg border ${cls}`}><Icon className="h-4 w-4" /></span>
      <div className="min-w-0 flex-1">
        <p data-testid="manage-device-name" className="truncate text-sm font-medium text-txt">{d.name}</p>
        <p className="truncate text-[11px] text-txt-3">{label}{d.last_heartbeat_at ? ` · heartbeat ${relativeTime(d.last_heartbeat_at, now)}` : ""}</p>
      </div>
      {canManage && (
        <div className="flex items-center gap-1">
          <IconBtn onClick={() => setRename(true)} label="Ubah nama" testId="manage-device-rename"><Pencil className="h-4 w-4" /></IconBtn>
          <IconBtn onClick={confirmRotate} label="Rotasi API key" testId="manage-device-rotate"><KeyRound className="h-4 w-4" /></IconBtn>
          <IconBtn onClick={() => toggle.mutate()} label={d.is_active ? "Nonaktifkan" : "Aktifkan"} testId="manage-device-toggle" danger={d.is_active}><Power className="h-4 w-4" /></IconBtn>
        </div>
      )}
      {rename && <DeviceDialog open onClose={() => setRename(false)} storeId={storeId} device={d} onCreated={() => undefined} />}
    </li>
  );
};

const CameraLine = ({ c, storeId, devices, canManage }: { c: CameraOut; storeId: string; devices: DeviceOut[]; canManage: boolean }) => {
  const [edit, setEdit] = useState(false);
  const del = useManageMutation(() => api.deleteCamera(c.camera_id), [["cameras", storeId]], "Kamera dihapus");
  const dev = devices.find((d) => d.device_id === c.device_id);
  return (
    <li data-testid="manage-camera-row" className="flex flex-wrap items-center gap-3 px-4 py-3">
      <span aria-hidden="true" className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-line bg-surface-2 text-txt-2"><Camera className="h-4 w-4" /></span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-txt"><span data-testid="manage-camera-name">{c.name}</span> <code className="font-mono ml-1 rounded bg-surface-2 px-1 text-[11px] text-txt-2" data-testid="manage-camera-external-id">{c.external_id}</code></p>
        <p className="truncate text-[11px] text-txt-3">{dev ? `Diproses oleh ${dev.name}` : "Perangkat belum ditentukan"}</p>
      </div>
      {canManage && (
        <div className="flex items-center gap-1">
          <IconBtn onClick={() => setEdit(true)} label="Ubah kamera" testId="manage-camera-edit"><Pencil className="h-4 w-4" /></IconBtn>
          <IconBtn onClick={() => window.confirm(`Hapus kamera ${c.name}?`) && del.mutate()} label="Hapus kamera" testId="manage-camera-delete" danger><Trash2 className="h-4 w-4" /></IconBtn>
        </div>
      )}
      {edit && <CameraDialog open onClose={() => setEdit(false)} storeId={storeId} devices={devices} camera={c} />}
    </li>
  );
};

export const StoreCard = ({ store, canManage, onKey }: Props) => {
  const devices = useQuery({ queryKey: ["devices", store.store_id], queryFn: () => api.devices(store.store_id) });
  const cameras = useCameras(store.store_id);
  const rules = useAlertRules(store.store_id);
  const [dialog, setDialog] = useState<"store" | "device" | "camera" | "rules" | null>(null);
  const close = () => setDialog(null);
  const list = (items: number, empty: string) => (items === 0 ? <p className="px-4 py-3 text-xs text-txt-3">{empty}</p> : null);
  return (
    <section data-testid="manage-store-card" className="card overflow-hidden">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
        <div className="min-w-0">
          <h3 data-testid="manage-store-name" className="truncate text-base font-semibold text-txt">{store.name}</h3>
          <p className="text-xs text-txt-2">Zona waktu {store.timezone} · <span data-testid="manage-store-hours">{store.open_time ? `buka ${store.open_time}–${store.close_time}` : "buka 24 jam"}</span>
            {rules.data && <> · <span data-testid="manage-store-alert-rules">{rules.data.is_default ? "alert bawaan" : "alert disesuaikan"}</span></>}</p>
        </div>
        {canManage && (
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={() => setDialog("rules")} disabled={!rules.data} className="ctl h-9" data-testid="manage-store-alert-rules-button"><Bell className="h-4 w-4" /> Aturan alert</button>
            <button type="button" onClick={() => setDialog("store")} className="ctl h-9" data-testid="manage-store-edit"><Pencil className="h-4 w-4" /> Ubah toko</button>
          </div>
        )}
      </header>
      <div className="grid gap-0 md:grid-cols-2 md:divide-x md:divide-line">
        <div>
          <div className="flex items-center justify-between px-4 pt-4 pb-1">
            <p className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-txt-2"><Cpu className="h-3.5 w-3.5" /> Perangkat ({devices.data?.length ?? "…"})</p>
            {canManage && <button type="button" onClick={() => setDialog("device")} className="ctl ctl-ghost h-8 text-emerald-brand" data-testid="manage-device-add"><Plus className="h-4 w-4" /> Tambah</button>}
          </div>
          <ul className="divide-y divide-line">
            {devices.data?.map((d) => <DeviceLine key={d.device_id} d={d} storeId={store.store_id} canManage={canManage} onKey={onKey} />)}
          </ul>
          {devices.isError && <p className="px-4 py-3 text-xs text-danger">Perangkat tidak dapat dimuat</p>}
          {devices.data && list(devices.data.length, "Belum ada perangkat. Tambahkan perangkat untuk mendapatkan API key edge agent.")}
        </div>
        <div>
          <div className="flex items-center justify-between px-4 pt-4 pb-1">
            <p className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-txt-2"><Camera className="h-3.5 w-3.5" /> Kamera ({cameras.data?.length ?? "…"})</p>
            {canManage && <button type="button" onClick={() => setDialog("camera")} className="ctl ctl-ghost h-8 text-emerald-brand" data-testid="manage-camera-add"><Plus className="h-4 w-4" /> Tambah</button>}
          </div>
          <ul className="divide-y divide-line">
            {cameras.data?.map((c) => <CameraLine key={c.camera_id} c={c} storeId={store.store_id} devices={devices.data ?? []} canManage={canManage} />)}
          </ul>
          {cameras.isError && <p className="px-4 py-3 text-xs text-danger">Kamera tidak dapat dimuat</p>}
          {cameras.data && list(cameras.data.length, "Belum ada kamera. camera_id harus cocok dengan config edge agent.")}
        </div>
      </div>
      {dialog === "store" && <StoreDialog open onClose={close} tenantId={store.tenant_id} store={store} />}
      {dialog === "rules" && rules.data && <AlertRulesDialog open onClose={close} storeId={store.store_id} storeName={store.name} rules={rules.data} />}
      {dialog === "device" && <DeviceDialog open onClose={close} storeId={store.store_id} onCreated={onKey} />}
      {dialog === "camera" && <CameraDialog open onClose={close} storeId={store.store_id} devices={devices.data ?? []} />}
    </section>
  );
};
