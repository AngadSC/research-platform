import { describe, expect, it } from "vitest";
import { plural, relativeTime } from "@/lib/format";
import { daysUntil, relativeDays } from "@/lib/ethics";

const NOW = Date.parse("2026-11-04T12:00:00Z");
const ago = (secs: number) => new Date(NOW - secs * 1000).toISOString();
const ahead = (secs: number) => new Date(NOW + secs * 1000).toISOString();

describe("plural", () => {
  it("uses the singular only for 1", () => {
    expect(plural(1, "day")).toBe("1 day");
    expect(plural(0, "day")).toBe("0 days");
    expect(plural(2, "day")).toBe("2 days");
    expect(plural(3, "person", "people")).toBe("3 people");
  });
});

describe("relativeDays", () => {
  it("never prints day(s)", () => {
    expect(relativeDays(1)).toBe("tomorrow");
    expect(relativeDays(2)).toBe("in 2 days");
    expect(relativeDays(-3)).toBe("3 days ago");
    expect(daysUntil("2026-11-29", new Date(2026, 10, 4))).toBe(25);
  });
});

describe("relativeTime", () => {
  it("formats future and past times in the browser locale", () => {
    expect(relativeTime(ahead(25 * 86400), NOW)).toBe("in 25 days");
    expect(relativeTime(ago(3 * 3600), NOW)).toBe("3 hours ago");
    expect(relativeTime(ago(5 * 60), NOW)).toBe("5 minutes ago");
  });

  it("says just now for very recent times", () => {
    expect(relativeTime(ago(10), NOW)).toBe("just now");
  });
});
