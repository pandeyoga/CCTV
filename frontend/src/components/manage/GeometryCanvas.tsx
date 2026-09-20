import { useRef, type MouseEvent, type ReactNode } from "react";
import type { EnterSide, Point } from "../../api/types";

/** Normalized (0..1, origin top-left, y down) drawing surface over a camera snapshot; 16:9 grid when no snapshot. */
interface Props {
  imageUrl: string | null;
  onClick?: (p: Point) => void;
  children: ReactNode; // SVG overlay content in viewBox 0..1000 x 0..1000 (scaled)
  testId: string;
  hint?: string;
}

export const clamp01 = (v: number) => Math.min(1, Math.max(0, Math.round(v * 1000) / 1000));
export const px = (v: number) => v * 1000;

export const GeometryCanvas = ({ imageUrl, onClick, children, testId, hint }: Props) => {
  const ref = useRef<HTMLDivElement>(null);
  const handle = (e: MouseEvent<HTMLDivElement>) => {
    if (!onClick || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    onClick([clamp01((e.clientX - r.left) / r.width), clamp01((e.clientY - r.top) / r.height)]);
  };
  return (
    <div>
      <div ref={ref} onClick={handle} data-testid={testId} role="img" aria-label="Kanvas kamera"
        className={`relative w-full overflow-hidden rounded-xl border border-line bg-ink ${onClick ? "cursor-crosshair" : ""}`} style={{ aspectRatio: "16 / 9" }}>
        {imageUrl ? (
          <img src={imageUrl} alt="Snapshot kamera" className="absolute inset-0 h-full w-full object-fill select-none" draggable={false} />
        ) : (
          <div className="absolute inset-0 grid-bg" />
        )}
        <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" className="absolute inset-0 h-full w-full">{children}</svg>
      </div>
      {hint && <p className="mt-2 text-[11px] text-txt-3" data-testid={`${testId}-hint`}>{hint}</p>}
    </div>
  );
};

/** Arrow from the line midpoint towards the ENTER side (left/right of a->b on screen, y down). */
export const LineOverlay = ({ a, b, enterSide }: { a: Point | null; b: Point | null; enterSide: EnterSide }) => {
  if (!a) return null;
  if (!b) return <circle cx={px(a[0])} cy={px(a[1])} r={10} fill="#10B981" stroke="#fff" strokeWidth={3} />;
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1;
  const nx = (enterSide === "right" ? -dy : dy) / len, ny = (enterSide === "right" ? dx : -dx) / len;
  const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2;
  const tip: Point = [mx + nx * 0.12, my + ny * 0.12];
  return (
    <g>
      <line x1={px(a[0])} y1={px(a[1])} x2={px(b[0])} y2={px(b[1])} stroke="#10B981" strokeWidth={6} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      <line x1={px(mx)} y1={px(my)} x2={px(tip[0])} y2={px(tip[1])} stroke="#F59E0B" strokeWidth={5} strokeDasharray="10 8" />
      <circle cx={px(tip[0])} cy={px(tip[1])} r={14} fill="#F59E0B" />
      <text x={px(tip[0])} y={px(tip[1]) - 24} fill="#F59E0B" fontSize={36} fontWeight={700} textAnchor="middle" style={{ paintOrder: "stroke", stroke: "#111", strokeWidth: 8 }}>MASUK</text>
      <circle cx={px(a[0])} cy={px(a[1])} r={10} fill="#fff" />
      <text x={px(a[0])} y={px(a[1]) - 18} fill="#fff" fontSize={30} textAnchor="middle" style={{ paintOrder: "stroke", stroke: "#111", strokeWidth: 6 }}>A</text>
      <circle cx={px(b[0])} cy={px(b[1])} r={10} fill="#fff" />
      <text x={px(b[0])} y={px(b[1]) - 18} fill="#fff" fontSize={30} textAnchor="middle" style={{ paintOrder: "stroke", stroke: "#111", strokeWidth: 6 }}>B</text>
    </g>
  );
};

export const PolygonOverlay = ({ points, color = "#38BDF8", label, closed }: { points: Point[]; color?: string; label?: string; closed: boolean }) => {
  if (points.length === 0) return null;
  const d = points.map((p) => `${px(p[0])},${px(p[1])}`).join(" ");
  const cx = points.reduce((s, p) => s + p[0], 0) / points.length, cy = points.reduce((s, p) => s + p[1], 0) / points.length;
  return (
    <g>
      {closed && points.length >= 3
        ? <polygon points={d} fill={color} fillOpacity={0.25} stroke={color} strokeWidth={5} />
        : <polyline points={d} fill="none" stroke={color} strokeWidth={5} strokeDasharray="12 8" />}
      {points.map((p, i) => <circle key={i} cx={px(p[0])} cy={px(p[1])} r={9} fill="#fff" stroke={color} strokeWidth={3} />)}
      {label && points.length >= 3 && <text x={px(cx)} y={px(cy)} fill="#fff" fontSize={34} fontWeight={600} textAnchor="middle" style={{ paintOrder: "stroke", stroke: "#111", strokeWidth: 8 }}>{label}</text>}
    </g>
  );
};
