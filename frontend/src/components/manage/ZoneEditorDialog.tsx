import { useState, type FormEvent } from "react";
import { Check, Plus, Trash2, Undo2 } from "lucide-react";
import { api } from "../../api/client";
import type { CameraOut, Point, ZoneOut } from "../../api/types";
import { useCameraZones, useLines, useSnapshotUrl } from "../../hooks/useGeometry";
import { useManageMutation } from "../../hooks/useManageData";
import { GeometryCanvas, LineOverlay, PolygonOverlay } from "./GeometryCanvas";
import { Modal, inputCls } from "./Modal";

interface Props {
  open: boolean;
  onClose: () => void;
  camera: CameraOut;
  canManage: boolean;
}

const COLORS = ["#38BDF8", "#A78BFA", "#F472B6", "#FBBF24", "#34D399"];

export const ZoneEditorDialog = ({ open, onClose, camera, canManage }: Props) => {
  const zones = useCameraZones(camera.camera_id);
  const lines = useLines(camera.camera_id);
  const snap = useSnapshotUrl(camera.camera_id, camera.snapshot_at);
  const [draft, setDraft] = useState<Point[] | null>(null);
  const [name, setName] = useState("");
  const [extId, setExtId] = useState("");
  const [editing, setEditing] = useState<ZoneOut | null>(null);
  const keys = [["zones", "camera", camera.camera_id], ["zones", "store", camera.store_id], ["zones", "occupancy"]];
  const reset = () => { setDraft(null); setName(""); setExtId(""); setEditing(null); };
  const create = useManageMutation(() => editing
    ? api.patchZone(editing.zone_id, { name, polygon: draft! })
    : api.createZone(camera.camera_id, { external_id: extId, name, polygon: draft! }), keys, editing ? "Zona diperbarui" : "Zona ditambahkan; edge agent memuatnya pada polling berikutnya", reset);
  const del = useManageMutation((id: string) => api.deleteZone(id), keys, "Zona dihapus (beserta sampel okupansinya)");
  const startEdit = (z: ZoneOut) => { setEditing(z); setDraft(z.polygon); setName(z.name); setExtId(z.external_id); };
  const submit = (e: FormEvent) => { e.preventDefault(); if (draft && draft.length >= 3) create.mutate(); };
  const line = lines.data?.[0];
  return (
    <Modal open={open} onClose={onClose} testId="zone-editor-dialog" title={`Zona okupansi · ${camera.name}`}
      description="Klik untuk menambah titik poligon (min. 3), lalu beri nama dan simpan. Edge agent mengirim jumlah orang di zona tiap 10 detik.">
      <div className="space-y-4">
        <GeometryCanvas imageUrl={snap.url} onClick={canManage && draft !== null ? (p) => setDraft([...draft, p]) : undefined} testId="zone-editor-canvas"
          hint={snap.status === "none" ? "Belum ada snapshot dari edge agent; poligon digambar pada kanvas kosong 0..1." : undefined}>
          {line && <LineOverlay a={[line.ax, line.ay]} b={[line.bx, line.by]} enterSide={line.enter_side} />}
          {(zones.data ?? []).filter((z) => z.zone_id !== editing?.zone_id).map((z, i) => <PolygonOverlay key={z.zone_id} points={z.polygon} closed label={z.name} color={COLORS[i % COLORS.length]} />)}
          {draft && <PolygonOverlay points={draft} closed={draft.length >= 3} color="#F97316" label={name || undefined} />}
        </GeometryCanvas>
        {draft === null ? (
          <div className="flex flex-wrap items-center justify-between gap-2">
            <ul className="flex flex-wrap gap-2" data-testid="zone-editor-list">
              {zones.data?.length === 0 && <li className="text-xs text-txt-3" data-testid="zone-editor-empty">Belum ada zona pada kamera ini.</li>}
              {zones.data?.map((z, i) => (
                <li key={z.zone_id} data-testid="zone-editor-item" className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface-2 px-2.5 py-1 text-xs text-txt">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: COLORS[i % COLORS.length] }} aria-hidden="true" />
                  <button type="button" onClick={() => canManage && startEdit(z)} className="font-medium hover:underline" data-testid="zone-editor-item-name">{z.name}</button>
                  <code className="font-mono text-[10px] text-txt-3">{z.external_id}</code>
                  {canManage && <button type="button" aria-label={`Hapus zona ${z.name}`} onClick={() => window.confirm(`Hapus zona ${z.name} beserta sampelnya?`) && del.mutate(z.zone_id)} className="text-danger" data-testid="zone-editor-item-delete"><Trash2 className="h-3.5 w-3.5" /></button>}
                </li>
              ))}
            </ul>
            {canManage && <button type="button" onClick={() => setDraft([])} className="ctl ctl-ink h-9" data-testid="zone-editor-new"><Plus className="h-4 w-4" aria-hidden="true" /> Zona baru</button>}
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-3" data-testid="zone-editor-form">
            <div className="grid gap-3 sm:grid-cols-2">
              <input required maxLength={128} placeholder="Nama zona (mis. Antrean kasir)" value={name} onChange={(e) => setName(e.target.value)} className={inputCls} data-testid="zone-editor-name-input" />
              <input required disabled={Boolean(editing)} pattern="[A-Za-z0-9_.-]+" maxLength={64} placeholder="zone_id (mis. kasir-1)" value={extId} onChange={(e) => setExtId(e.target.value)} className={`${inputCls} font-mono disabled:text-txt-3`} data-testid="zone-editor-id-input" />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-txt-2 tnum" data-testid="zone-editor-points">{draft.length} titik{draft.length < 3 ? " (min. 3)" : ""}</span>
              <button type="button" onClick={() => setDraft(draft.slice(0, -1))} disabled={draft.length === 0} className="ctl ctl-ghost h-9" data-testid="zone-editor-undo"><Undo2 className="h-4 w-4" aria-hidden="true" /> Hapus titik terakhir</button>
              <div className="ml-auto flex gap-2">
                <button type="button" onClick={reset} className="ctl h-9" data-testid="zone-editor-dialog-cancel">Batal</button>
                <button type="submit" disabled={draft.length < 3 || create.isPending} className="ctl ctl-ink h-9" data-testid="zone-editor-dialog-submit"><Check className="h-4 w-4" aria-hidden="true" /> {create.isPending ? "Menyimpan…" : editing ? "Simpan zona" : "Tambah zona"}</button>
              </div>
            </div>
          </form>
        )}
        {zones.isError && <p className="text-xs text-danger" data-testid="zone-editor-error">Zona tidak dapat dimuat.</p>}
      </div>
    </Modal>
  );
};
