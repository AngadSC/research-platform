import { describe, expect, it } from "vitest";
import { vendorLinks } from "./vendors";

describe("vendorLinks", () => {
  it("encodes the term, and a slash cannot break VWR's path-style search", () => {
    const links = Object.fromEntries(vendorLinks("A/1 x&y").map((v) => [v.name, v.href]));
    expect(links["Thermo Fisher"]).toBe(
      "https://www.thermofisher.com/search/results?query=A%2F1%20x%26y",
    );
    expect(links["VWR"]).toBe("https://www.vwr.com/ca/en/search/A%201%20x%26y");
    expect(Object.keys(links)).toEqual([
      "Thermo Fisher",
      "Fisher Scientific",
      "Sigma-Aldrich",
      "VWR",
    ]);
  });
});
