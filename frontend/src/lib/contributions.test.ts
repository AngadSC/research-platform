import { describe, expect, it } from "vitest";
import { buildWeeks, isoDay, level, monthLabels, parseDay } from "@/lib/contributions";

describe("contribution graph helpers", () => {
  it("reads and writes plain dates without time-zone shifts", () => {
    expect(isoDay(parseDay("2026-03-01"))).toBe("2026-03-01");
    expect(parseDay("2026-11-08").getDay()).toBe(0); // a Sunday
  });

  it("shades by quarter of the busiest day", () => {
    expect(level(0, 8)).toBe(0);
    expect(level(1, 8)).toBe(1);
    expect(level(2, 8)).toBe(1);
    expect(level(3, 8)).toBe(2);
    expect(level(6, 8)).toBe(3);
    expect(level(8, 8)).toBe(4);
    expect(level(5, 0)).toBe(0);
  });

  it("lays out Sunday-first weeks and leaves the days after today empty", () => {
    // Sunday Nov 1 to Wednesday Nov 11, 2026
    const weeks = buildWeeks("2026-11-01", "2026-11-11", [
      { date: "2026-11-03", count: 4 },
      { date: "2026-11-10", count: 1 },
    ]);
    expect(weeks).toHaveLength(2);
    expect(weeks[0]![0]!.date).toBe("2026-11-01");
    expect(weeks[0]![2]).toMatchObject({ date: "2026-11-03", count: 4, level: 4 });
    expect(weeks[1]![2]).toMatchObject({ date: "2026-11-10", count: 1, level: 1 });
    expect(weeks[1]![3]!.future).toBe(false); // today
    expect(weeks[1]![4]!.future).toBe(true);
    expect(weeks[1]![6]!.date).toBe("2026-11-14");
  });

  it("labels each month once, skipping a cramped first label", () => {
    const weeks = buildWeeks("2026-10-25", "2026-12-12", []);
    const labels = monthLabels(weeks).map((m) => m.index);
    // Oct 25 (col 0) is followed by Nov 1 (col 1): too close, so October is dropped.
    expect(labels).toEqual([1, 6]);
  });
});
