import { describe, expect, it } from "vitest";
import type { CalendarItem } from "@/lib/api-types";
import { calendarHref, itemsOn, monthGrid, toLocalInput } from "./calendar";
import { localDateISO } from "./format";

const item = (over: Partial<CalendarItem>) =>
  ({ kind: "event", id: "i1", date: "2026-03-10", end_date: null, ...over }) as CalendarItem;

describe("calendar", () => {
  it("fills whole weeks around the month, Sunday first", () => {
    const days = monthGrid(2026, 1); // February 2026 starts on a Sunday and fits 4 weeks
    expect(days).toHaveLength(28);
    expect(localDateISO(days[0]!)).toBe("2026-02-01");
    expect(localDateISO(days[27]!)).toBe("2026-02-28");
    const may = monthGrid(2026, 4); // May 2026 starts on a Friday
    expect(may).toHaveLength(42);
    expect(localDateISO(may[0]!)).toBe("2026-04-26");
  });

  it("shows a multi-day event on each of its days only", () => {
    const span = item({ date: "2026-03-10", end_date: "2026-03-12" });
    expect(itemsOn([span], "2026-03-11")).toEqual([span]);
    expect(itemsOn([span], "2026-03-13")).toEqual([]);
    expect(itemsOn([item({})], "2026-03-11")).toEqual([]);
  });

  it("puts a meeting on the viewer's local day, whatever day the server sent", () => {
    const start = new Date(2026, 2, 10, 23, 30);
    const meeting = item({ date: "2026-03-11", starts_at: start.toISOString() });
    expect(itemsOn([meeting], "2026-03-10")).toEqual([meeting]);
    expect(itemsOn([meeting], "2026-03-11")).toEqual([]);
    expect(toLocalInput(start)).toBe("2026-03-10T23:30");
  });

  it("links each kind to its source; lab events open in place", () => {
    const at = (kind: CalendarItem["kind"]) =>
      calendarHref("L", item({ kind, project_id: "P", id: "X" }));
    expect(at("deadline")).toBe("/labs/L/projects/P/overview");
    expect(at("meeting")).toBeNull();
    expect(at("task")).toBe("/labs/L/projects/P/tasks?task=X");
    expect(at("funding")).toBe("/labs/L/projects/P/workflow/funding");
    expect(at("inventory")).toBe("/labs/L/inventory");
    expect(at("ethics")).toBe("/labs/L/ethics/X");
    expect(at("event")).toBeNull();
  });
});
