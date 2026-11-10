import { describe, expect, it } from "vitest";
import { navItems } from "@/lib/nav";

describe("navItems", () => {
  it("drops Inventory for a lab with inventory turned off", () => {
    const labels = (on: boolean) => navItems("lab1", [], on).map((n) => n.label);
    expect(labels(true)).toContain("Inventory");
    expect(labels(false)).not.toContain("Inventory");
  });
});
