import { useState } from "react";
import { ArrowLeftRight, Trash2 } from "lucide-react";
import { api } from "../../api/client";
import type { CameraOut, EnterSide, LineOut, Point, ZoneOut } from "../../api/types";
import { useCameraZones, useLines, useSnapshotUrl } from "../../hooks/useGeometry";
import { useManageMutation } from "../../hooks/useManageData";
import { relativeTime } from "../../lib/time";
import { useNow } from "../../hooks/useNow";
import { GeometryCanvas, LineOverlay, PolygonOverlay } from "./GeometryCanvas";
import { Modal } from "./Modal";

interface Props {
  open: boolean;
  onClose: () => void;
  camera: CameraOut;
  canManage: boolean;
}

const SNAPSHOT_HINT = "Belum ada snapshot dari edge agent (dikirim tiap 10 menit saat agent berjalan). Garis tetap bisa digambar pada kanvas kosong 0..1.";

export const LineEditorDialog = ({ open, onClose, camera, canManage }: Props) => {
  const now = useNow();
  const lines = useLines(camera.camera_id);
  const zones = useCameraZones(camera.camera_id);
  const snap = useSnapshotUrl(camera.camera_id, camera.snapshot_at);
  const existing: LineOut | undefined = lines.data?.[0];
  const [a, setA] = useState<Point | null>(existing ? [existing.ax, existing.ay] : null);
  const [b, setB] = useState<Point | null>(existing ? [existing.bx, existing.by] : null);
  const [side, setSide] = useState<EnterSide>(existing?.enter_side ?? "left");
  const [lineId, setLineId] = useState(existing?.line_id ?? "door-1");
  const [seeded, setSeeded] = useState(Boolean(existing));
  if (!seeded && existing) { setA([existing.ax, existing.ay]); setB([existing.bx, existing.by]); setSide(existing.enter_side); setLineId(existing.line_id); setSeeded(true); }
  const keys = [["lines", camera.camera_id]];
  const save = useManageMutation(() => api.putLine(camera.camera_id, lineId, { ax: a![0], ay: a![1], bx: b![0], by: b![1], enter_side: side }), keys, "Garis hitung disimpan; edge agent memuatnya pada polling berikutnya", onClose);
  const del = useManageMutation(() => api.deleteLine(camera.camera_id, existing!.line_id), keys, "Garis hitung dihapus", onClose);
  const click = (p: Point) => {
    if (!canManage) return;
    if (!a || (a && b)) { setA(p); setB(null); } else setB(p);
  };
  const dirty = !existing || !a || !b || a[0] !== existing.ax || a[1] !== existing.ay || b[0] !== existing.bx || b[1] !== existing.by || side !== existing.enter_side || lineId !== existing.line_id;
  return (
    <Modal open={open} onClose={onClose} testId="line-editor-dialog" title={`Garis hitung · ${camera.name}`}
      description="Klik dua titik (A lalu B). Orang yang menyeberang dan berakhir di sisi MASUK dihitung sebagai masuk. Koordinat 0..1, dimuat otomatis oleh edge agent.">
      <div className="space-y-4">
        <GeometryCanvas imageUrl={snap.url} onClick={canManage ? click : undefined} testId="line-editor-canvas"
          hint={snap.status === "none" ? SNAPSHOT_HINT : camera.snapshot_at ? `Snapshot ${relativeTime(camera.snapshot_at, now)}` : undefined}>
          {(zones.data ?? []).map((z: ZoneOut) => <PolygonOverlay key={z.zone_id} points={z.polygon} closed label={z.name} />)}
          <LineOverlay a={a} b={b} enterSide={side} />
        </GeometryCanvas>
        <div className="flex flex-wrap items-center gap-2 text-xs text-txt-2">
          <span data-testid="line-editor-coords" className="tnum">
            {a && b ? `A (${a[0]}, ${a[1]}) → B (${b[0]}, ${b[1]})` : a ? "Titik A ditentukan — klik titik B" : "Klik titik A"}
          </span>
          <span className="ml-auto inline-flex items-center gap-2">
            <label className="text-[11px] text-txt-3">line_id</label>
            <input value={lineId} onChange={(e) => setLineId(e.target.value)} disabled={!canManage || Boolean(existing)} pattern="[A-Za-z0-9_.-]+" maxLength={64}
              className="login-input h-8 w-28 rounded-ctl border border-line bg-surface px-2 font-mono text-xs text-txt disabled:text-txt-3" data-testid="line-editor-id-input" />
          </span>
        </div>
        {canManage && (
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={() => setSide(side === "left" ? "right" : "left")} className="ctl h-9" data-testid="line-editor-flip" disabled={!a || !b}>
              <ArrowLeftRight className="h-4 w-4" aria-hidden="true" /> Balik arah masuk (<span data-testid="line-editor-side">{side === "left" ? "kiri" : "kanan"}</span>)
            </button>
            <button type="button" onClick={() => { setA(null); setB(null); }} className="ctl ctl-ghost h-9" data-testid="line-editor-clear" disabled={!a}>Gambar ulang</button>
            {existing && (
              <button type="button" onClick={() => window.confirm("Hapus garis hitung? Edge agent akan memakai garis lokal (YAML) bila ada.") && del.mutate()} className="ctl ctl-ghost h-9 text-danger" data-testid="line-editor-delete">
                <Trash2 className="h-4 w-4" aria-hidden="true" /> Hapus
              </button>
            )}
            <div className="ml-auto flex gap-2">
              <button type="button" onClick={onClose} className="ctl h-9" data-testid="line-editor-dialog-cancel">Batal</button>
              <button type="button" onClick={() => save.mutate()} disabled={!a || !b || !dirty || save.isPending || !lineId} className="ctl ctl-ink h-9" data-testid="line-editor-dialog-submit">
                {save.isPending ? "Menyimpan…" : "Simpan garis"}
              </button>
            </div>
          </div>
        )}
        {lines.isError && <p className="text-xs text-danger" data-testid="line-editor-error">Garis tidak dapat dimuat.</p>}
      </div>
    </Modal>
  );
};
