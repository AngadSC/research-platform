import { describe, expect, it } from "vitest";
import { findApprovalNumbers } from "@/lib/approvalNumber";

describe("findApprovalNumbers", () => {
  it("reads a board and a number from a description", () => {
    expect(findApprovalNumbers("Ethics: REB Pro00151738, renewed in May.")).toEqual([
      { number: "Pro00151738", board: "REB" },
    ]);
    expect(findApprovalNumbers("irb #2023-0456 applies")).toEqual([
      { number: "2023-0456", board: "IRB" },
    ]);
  });
  it("finds a bare Pro number and does not list one twice", () => {
    expect(findApprovalNumbers("Pro00151738 and REB Pro00151738")).toEqual([
      { number: "Pro00151738", board: "REB" },
    ]);
    expect(findApprovalNumbers("see Pro00099999")).toEqual([{ number: "Pro00099999", board: "" }]);
  });
  it("finds nothing in ordinary text", () => {
    expect(findApprovalNumbers("A study of sleep. The REB reviews it yearly.")).toEqual([]);
  });
});
