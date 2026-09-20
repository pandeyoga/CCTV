import { busiestHours, dailyCsv, formatPct, peakDay, pctChange } from "./report";
import type { RangeReportOut } from "../api/types";

const report: RangeReportOut = {
  store_id: "s", timezone: "Asia/Jakarta", open_time: null, close_time: null, outside_hours_excluded: 0,
  current: { from_date: "2026-06-03", to_date: "2026-06-04", days: 2, enter: 3, exit: 1 },
  previous: { from_date: "2026-06-01", to_date: "2026-06-02", days: 2, enter: 2, exit: 0 },
  daily: [{ date: "2026-06-03", enter: 2, exit: 1 }, { date: "2026-06-04", enter: 1, exit: 0 }],
  hourly_profile: Array.from({ length: 24 }, (_, hour) => ({ hour, enter: hour === 9 ? 2 : hour === 0 ? 1 : 0, exit: hour === 17 ? 1 : 0 })),
};

test("pctChange and formatPct", () => {
  expect(pctChange(3, 2)).toBe(50);
  expect(pctChange(1, 4)).toBe(-75);
  expect(pctChange(5, 0)).toBeNull();
  expect(formatPct(50)).toBe("+50%");
  expect(formatPct(-12.5)).toBe("-12,5%");
  expect(formatPct(null)).toBe("—");
});

test("busiestHours excludes empty hours and sorts by enter desc", () => {
  expect(busiestHours(report).map((h) => h.hour)).toEqual([9, 0]);
});

test("peakDay picks the day with most entries", () => {
  expect(peakDay(report)?.date).toBe("2026-06-03");
  expect(peakDay({ ...report, daily: [{ date: "2026-06-03", enter: 0, exit: 0 }] })).toBeNull();
});

test("dailyCsv has BOM, header and one row per day with quoted fields", () => {
  const csv = dailyCsv(report, 'Toko "Pilot"');
  expect(csv.startsWith("\uFEFF\"toko\"")).toBe(true);
  const rows = csv.trim().split("\r\n");
  expect(rows).toHaveLength(3);
  expect(rows[1]).toBe('"Toko ""Pilot""","Asia/Jakarta","2026-06-03","2","1","1"');
});
