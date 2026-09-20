import type { RangeReportOut } from "../api/types";

/** Percent change current vs previous; null when the previous period is 0 (no meaningful ratio). */
export function pctChange(current: number, previous: number): number | null {
  if (previous === 0) return null;
  return Math.round(((current - previous) / previous) * 1000) / 10;
}

export function formatPct(p: number | null): string {
  if (p === null) return "—";
  const sign = p > 0 ? "+" : "";
  return `${sign}${p.toLocaleString("id-ID", { maximumFractionDigits: 1 })}%`;
}

/** Busiest hours by `enter`, descending; hours with 0 entries are excluded. */
export function busiestHours(r: RangeReportOut, limit = 5): RangeReportOut["hourly_profile"] {
  return [...r.hourly_profile].filter((h) => h.enter > 0).sort((a, b) => b.enter - a.enter || a.hour - b.hour).slice(0, limit);
}

export function hourRange(h: number): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(h)}:00–${pad(h)}:59`;
}

/** Day with the highest `enter`; null when every day is 0. */
export function peakDay(r: RangeReportOut): RangeReportOut["daily"][number] | null {
  const best = r.daily.reduce<RangeReportOut["daily"][number] | null>((acc, d) => (acc === null || d.enter > acc.enter ? d : acc), null);
  return best && best.enter > 0 ? best : null;
}

/** RFC 4180-ish CSV of the daily buckets (semicolon-free, quoted header). UTF-8 BOM so Excel (id-ID) opens it correctly. */
export function dailyCsv(r: RangeReportOut, storeName: string): string {
  const esc = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`;
  const lines = [["toko", "zona_waktu", "tanggal", "masuk", "keluar", "selisih"].map(esc).join(",")];
  for (const d of r.daily) lines.push([storeName, r.timezone, d.date, d.enter, d.exit, d.enter - d.exit].map(esc).join(","));
  return "\uFEFF" + lines.join("\r\n") + "\r\n";
}

export function downloadText(filename: string, text: string, mime = "text/csv;charset=utf-8"): void {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
