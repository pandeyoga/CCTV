import { addDays, formatTimeInTz, hourLabel, isStale, relativeTime, todayInTz } from "./time";

describe("store-timezone date helpers", () => {
  test("todayInTz uses the store timezone, not the browser", () => {
    const utc = new Date("2026-06-01T17:30:00Z"); // 00:30 on June 2 in Asia/Jakarta (UTC+7)
    expect(todayInTz("Asia/Jakarta", utc)).toBe("2026-06-02");
    expect(todayInTz("UTC", utc)).toBe("2026-06-01");
  });

  test("addDays crosses month boundaries", () => {
    expect(addDays("2026-06-30", 1)).toBe("2026-07-01");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
  });

  test("formatTimeInTz renders in store local time", () => {
    expect(formatTimeInTz("2026-06-01T02:15:00Z", "Asia/Jakarta")).toBe("09.15.00");
  });

  test("stale detection at 5 minutes", () => {
    const now = new Date("2026-06-01T10:00:00Z");
    expect(isStale("2026-06-01T09:56:00Z", now)).toBe(false);
    expect(isStale("2026-06-01T09:54:00Z", now)).toBe(true);
    expect(isStale(null, now)).toBe(true);
  });

  test("relativeTime and hourLabel", () => {
    const now = new Date("2026-06-01T10:00:00Z");
    expect(relativeTime("2026-06-01T09:59:30Z", now)).toBe("30 dtk lalu");
    expect(relativeTime("2026-06-01T08:00:00Z", now)).toBe("2 jam lalu");
    expect(hourLabel("2026-06-01T09:00:00+07:00")).toBe("09");
  });
});
