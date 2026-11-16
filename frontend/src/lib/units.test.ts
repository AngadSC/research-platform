import { describe, expect, it } from "vitest";
import { compatibleUnits, convert, trimNumber } from "@/lib/units";

describe("units", () => {
  it("converts within a kind of unit and refuses across kinds", () => {
    expect(convert(10, "mL", "L")).toBeCloseTo(0.01);
    expect(convert(500, "ug", "mg")).toBeCloseTo(0.5);
    expect(convert(2, "vials", "vials")).toBe(2);
    expect(convert(1, "mL", "g")).toBeNull();
    expect(convert(1, "vials", "mL")).toBeNull();
  });
  it("offers the units that convert, and none for counted things", () => {
    expect(compatibleUnits("L")).toContain("mL");
    expect(compatibleUnits("g")).toContain("mg");
    expect(compatibleUnits("vials")).toEqual([]);
  });
  it("trims trailing zeros from stock numbers", () => {
    expect(trimNumber("99.990000")).toBe("99.99");
    expect(trimNumber("100.000000")).toBe("100");
  });
});
