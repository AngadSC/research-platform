import { describe, expect, it } from "vitest";
import { initials } from "./identity";

describe("initials", () => {
  it.each([
    ["Lee Lead (FAKE)", "LL"],
    ["Pat", "P"],
    ["sam.jones@uni.edu", "S"],
    ["", ""],
  ])("%s gives %s", (name, want) => {
    expect(initials(name)).toBe(want);
  });
});
