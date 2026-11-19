import { describe, expect, it } from "vitest";
import type { StatsResult } from "@/lib/stats/contract";
import { effectLabel } from "@/lib/stats/effectLabel";

const at = (summary: string, test: StatsResult["test"] = "t_independent") =>
  effectLabel({ summary, test });

describe("effectLabel", () => {
  it("labels d and r by the usual cut-offs", () => {
    expect(at("t(38) = 2.3, p = .02, d = 1.73")).toBe("d = 1.73: a large difference");
    expect(at("t(38) = 2.3, p = .02, d = 0.5")).toBe("d = 0.5: a medium difference");
    expect(at("t(38) = 0.3, p = .7, d = 0.05")).toBe("d = 0.05: a very small difference");
    expect(at("U = 5, p = .02, r = .32", "mann_whitney")).toBe("r = .32: a medium effect");
    expect(at("r(28) = .12, p = .5", "correlation")).toBe("r = .12: a small relationship");
  });
  it("says nothing when there is no d or r", () => {
    expect(at("F(2, 9) = 3, p = .08")).toBeNull();
  });
});
