import { describe, expect, it } from "vitest";
import { fileSafe, tableCsv, tableTsv } from "@/lib/exportFiles";

const table = {
  title: "T",
  columns: ["Group", "Mean"],
  rows: [
    ["A, B", 1.5],
    ['say "hi"', null],
    ["=SUM(A1)", -2],
    ["-3.5", 4],
  ] as (string | number | null)[][],
};

describe("table exports", () => {
  it("quotes CSV cells, leaves blanks empty and starts with a byte-order mark", () => {
    const csv = tableCsv(table);
    expect(csv.charCodeAt(0)).toBe(0xfeff);
    const lines = csv.slice(1).trim().split("\r\n");
    expect(lines[0]).toBe("Group,Mean");
    expect(lines[1]).toBe('"A, B",1.5');
    expect(lines[2]).toBe('"say ""hi""",');
  });

  it("keeps text that looks like a formula as text, but not real numbers", () => {
    const lines = tableCsv(table).slice(1).trim().split("\r\n");
    expect(lines[3]).toBe("'=SUM(A1),-2");
    expect(lines[4]).toBe("-3.5,4");
  });

  it("copies as tab-separated text", () => {
    expect(tableTsv(table).split("\n")[0]).toBe("Group\tMean");
    expect(tableTsv(table).split("\n")[2]).toBe('say "hi"\t');
    // text that looks like a formula stays text when pasted into a spreadsheet
    expect(tableTsv(table).split("\n")[3]).toBe("'=SUM(A1)\t-2");
  });

  it("makes safe file names", () => {
    expect(fileSafe("Score by arm: Group means!")).toBe("score-by-arm-group-means");
    expect(fileSafe("///")).toBe("statistics");
  });
});
