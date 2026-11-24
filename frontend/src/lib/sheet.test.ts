import { describe, expect, it } from "vitest";
import {
  addr,
  colName,
  display,
  Evaluator,
  parseAddr,
  parseTsv,
  shiftCells,
  type Cell,
} from "@/lib/sheet";

const sheet = (o: Record<string, string>) =>
  new Evaluator(Object.fromEntries(Object.entries(o).map(([k, text]) => [k, { text } as Cell])));
const show = (o: Record<string, string>, ref = "Z1") => display(sheet({ ...o }).value(ref));

describe("addresses", () => {
  it("names columns past Z and parses references", () => {
    expect(colName(0)).toBe("A");
    expect(colName(25)).toBe("Z");
    expect(colName(26)).toBe("AA");
    expect(parseAddr("b12")).toEqual({ c: 1, r: 11 });
    expect(addr(27, 4)).toBe("AB5");
  });
});

describe("formulas", () => {
  it("does arithmetic with precedence, powers and percent", () => {
    expect(show({ Z1: "=1+2*3" })).toBe("7");
    expect(show({ Z1: "=(1+2)*3" })).toBe("9");
    expect(show({ Z1: "=2^3^2" })).toBe("64"); // left to right, like Excel
    expect(show({ Z1: "=-2^2" })).toBe("4"); // unary minus binds first, as in Excel
    expect(show({ Z1: "=50%" })).toBe("0.5");
  });
  it("sums, averages and counts ranges, skipping text", () => {
    const d = { A1: "1", A2: "2", A3: "x", A4: "5", Z1: "" };
    expect(show({ ...d, Z1: "=SUM(A1:A4)" })).toBe("8");
    expect(show({ ...d, Z1: "=AVERAGE(A1:A4)" })).toBe("2.6666666667");
    expect(show({ ...d, Z1: "=COUNT(A1:A4)" })).toBe("3");
    expect(show({ ...d, Z1: "=COUNTA(A1:A4)" })).toBe("4");
    expect(show({ ...d, Z1: "=MAX(A1:A4)" })).toBe("5");
    expect(show({ ...d, Z1: "=MEDIAN(A1:A4)" })).toBe("2");
  });
  it("follows references and reports errors", () => {
    expect(show({ A1: "4", B1: "=A1*2", Z1: "=B1+1" })).toBe("9");
    expect(show({ Z1: "=1/0" })).toBe("#DIV/0!");
    expect(show({ Z1: "=NOPE(1)" })).toBe("#NAME?");
    expect(show({ A1: "=B1", B1: "=A1" }, "A1")).toBe("#CIRC!");
    expect(show({ A1: "hi", Z1: "=A1+1" })).toBe("#VALUE!");
  });
  it("does IF, text and comparisons", () => {
    expect(show({ A1: "3", Z1: '=IF(A1>2,"big","small")' })).toBe("big");
    expect(show({ Z1: '="a"&"b"' })).toBe("ab");
    expect(show({ Z1: '=CONCAT("x","y")' })).toBe("xy");
    expect(show({ Z1: "=ROUND(2.567,1)" })).toBe("2.6");
  });
});

describe("display and editing", () => {
  it("formats numbers", () => {
    expect(display(0.256, "percent")).toBe("25.6%");
    expect(display(1234.5, "number")).toMatch(/1,?234\.50/);
  });
  it("moves cells and formulas when a row is inserted or removed", () => {
    const cells = { A1: { text: "1" }, A2: { text: "=A1+1" } } as Record<string, Cell>;
    const ins = shiftCells(cells, "row", 0, 1);
    expect(ins["A2"]!.text).toBe("1");
    expect(ins["A3"]!.text).toBe("=A2+1");
    const del = shiftCells(cells, "row", 0, -1);
    expect(del["A1"]!.text).toBe("=#REF!+1");
  });
  it("reads pasted tab-separated text", () => {
    expect(parseTsv("a\tb\n1\t2\n")).toEqual([
      ["a", "b"],
      ["1", "2"],
    ]);
  });
});
