import type { InstrumentSummary } from "./types";

const cell = (v: string | number | null | undefined) => {
  let s = v === null || v === undefined ? "" : String(v);
  // a text cell that starts like a formula would run in Excel; numbers are left alone
  if (typeof v === "string" && /^[=+\-@\t\r]/.test(s)) s = `'${s}`;
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

const line = (cells: (string | number | null | undefined)[]) => cells.map(cell).join(",");

/** "A1" -> ["A", 1]; sorts wells by row then column */
function splitWell(well: string): [string, number] {
  const m = /^([A-Za-z]+)(\d+)$/.exec(well);
  return m ? [(m[1] ?? "").toUpperCase(), Number(m[2])] : [well, 0];
}

/** CSV text of the first table, else of the first plate (one row per well), else null. */
export function summaryToCsv(summary: InstrumentSummary): string | null {
  if (summary.status !== "ok") return null;
  const table = summary.tables?.[0];
  if (table && table.columns.length > 0) {
    return [line(table.columns), ...table.rows.map(line)].join("\n");
  }
  const plate = summary.plates?.[0];
  if (plate) {
    const wells = Object.entries(plate.wells)
      .map(([well, value]) => ({ well, value, at: splitWell(well) }))
      .sort(
        (a, b) =>
          a.at[0].length - b.at[0].length || a.at[0].localeCompare(b.at[0]) || a.at[1] - b.at[1],
      );
    const head = ["Well", "Row", "Column", plate.unit ? `Value (${plate.unit})` : "Value"];
    return [line(head), ...wells.map((w) => line([w.well, w.at[0], w.at[1], w.value]))].join("\n");
  }
  return null;
}
