import { describe, expect, it } from "vitest";
import { applyOrder, moveId } from "@/components/layout/holdToReorder";

describe("saved order helpers", () => {
  it("moves an id to a place", () => {
    expect(moveId(["a", "b", "c"], "a", 2)).toEqual(["b", "c", "a"]);
  });
  it("applies a saved order, unknown items last", () => {
    expect(applyOrder(["a", "b", "c"], (x) => x, ["c", "a"])).toEqual(["c", "a", "b"]);
  });
});
