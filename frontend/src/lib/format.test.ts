import { describe, expect, it, vi } from "vitest";
import { localDateISO, plural, relativeTime, shortDate } from "@/lib/format";
import { daysUntil, relativeDays } from "@/lib/ethics";

const NOW = Date.parse("2026-11-04T12:00:00Z");
const ago = (secs: number) => new Date(NOW - secs * 1000).toISOString();
const ahead = (secs: number) => new Date(NOW + secs * 1000).toISOString();

describe("shortDate", () => {
  it("shows a bare date as that day, even west of UTC", () => {
    vi.stubEnv("TZ", "America/Edmonton");
    try {
      const day = new Date(2026, 10, 12).toLocaleDateString(undefined, { dateStyle: "medium" });
      expect(shortDate("2026-11-12")).toBe(day);
      expect(shortDate("2026-11-13T03:02:00Z")).toBe(day); // 8:02 pm on the 12th in Edmonton
    } finally {
      vi.unstubAllEnvs();
    }
  });
});

describe("localDateISO", () => {
  it("uses the local calendar day, not the UTC one", () => {
    // Evening in the Americas: UTC has already moved to the next day.
    const evening = {
      getFullYear: () => 2026,
      getMonth: () => 0,
      getDate: () => 5,
      toISOString: () => "2026-01-06T02:00:00.000Z",
    } as Date;
    expect(localDateISO(evening)).toBe("2026-01-05");
  });
});

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
