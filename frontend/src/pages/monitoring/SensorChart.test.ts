import { describe, expect, it } from "vitest";
import { dayTicks } from "./SensorChart";

describe("dayTicks", () => {
  it("puts a tick on each local midnight, including today's", () => {
    const end = new Date(2026, 10, 26, 15, 30).getTime(); // Thu 26 Nov, 15:30 local
    const ticks = dayTicks(end - 3 * 24 * 3_600_000, end);
    expect(ticks.map((t) => new Date(t).toDateString())).toEqual([
      "Thu Nov 26 2026",
      "Wed Nov 25 2026",
      "Tue Nov 24 2026",
    ]);
    expect(ticks.every((t) => new Date(t).getHours() === 0)).toBe(true);
  });
});
