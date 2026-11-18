import { describe, expect, it } from "vitest";
import { addDays, inThreeHours, isSnoozed, nextMonday } from "@/lib/snooze";

describe("snooze dates", () => {
  it("goes to the coming Monday, and past today if today is Monday", () => {
    expect(nextMonday("2026-11-11")).toBe("2026-11-16"); // Wednesday
    expect(nextMonday("2026-11-13")).toBe("2026-11-16"); // Friday
    expect(nextMonday("2026-11-15")).toBe("2026-11-16"); // Sunday
    expect(nextMonday("2026-11-16")).toBe("2026-11-23"); // Monday
  });
  it("adds days across a month end", () => {
    expect(addDays("2026-11-30", 1)).toBe("2026-12-01");
  });
});

describe("snooze moments", () => {
  it("rests until the moment passes, and only then", () => {
    const now = new Date("2026-11-17T12:00:00Z");
    expect(isSnoozed(null, now)).toBe(false);
    expect(isSnoozed("2026-11-17T15:00:00Z", now)).toBe(true);
    expect(isSnoozed("2026-11-17T11:59:00Z", now)).toBe(false);
    expect(new Date(inThreeHours(now)).getTime() - now.getTime()).toBe(3 * 3600_000);
  });
});
