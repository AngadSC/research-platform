import { describe, expect, it } from "vitest";
import { addDays, nextMonday } from "@/lib/snooze";

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
