import type { StatsTable } from "@/lib/stats/contract";

/** A text cell safe to open in a spreadsheet: text that starts like a formula is kept as text. */
const guard = (v: string) => (/^[=+\-@\t\r]/.test(v) && Number.isNaN(Number(v)) ? `'${v}` : v);

const csvCell = (v: string | number | null) => {
  if (v === null || v === undefined) return "";
  const text = typeof v === "number" ? String(v) : guard(v);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

const BOM = String.fromCharCode(0xfeff);

/** A table as CSV (UTF-8 with a byte-order mark so Excel reads accents correctly). */
export function tableCsv(t: StatsTable): string {
  const lines = [t.columns, ...t.rows].map((row) => row.map(csvCell).join(","));
  return `${BOM}${lines.join("\r\n")}\r\n`;
}

/** A table as tab-separated text, ready to paste into Excel, Sheets or Word. */
export function tableTsv(t: StatsTable): string {
  const cell = (v: string | number | null) => (typeof v === "string" ? guard(v) : (v ?? ""));
  return [t.columns.map(cell), ...t.rows.map((row) => row.map(cell))]
    .map((row) => row.join("\t"))
    .join("\n");
}

/** A chart's SVG as a standalone file. */
export function svgFile(svg: SVGSVGElement): Blob {
  const copy = svg.cloneNode(true) as SVGSVGElement;
  copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  return new Blob([new XMLSerializer().serializeToString(copy)], { type: "image/svg+xml" });
}

/** A name that is safe as a file name on any system. */
export const fileSafe = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 60) || "statistics";

export function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export const XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
