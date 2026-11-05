import { describe, expect, it } from "vitest";
import { initials, vivid } from "./identity";

describe("vivid", () => {
  it("gives the same id the same colour", () => {
    expect(vivid("project-1")).toEqual(vivid("project-1"));
  });
});

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
