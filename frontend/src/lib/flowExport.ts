import type { Flow } from "@/hooks/participants";

const esc = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** The rows of the flow summary, each with a flag when the count is small. */
export function flowRows(f: Flow): { label: string; count: number | null; small: boolean }[] {
  const row = (label: string, c: { count: number; small: boolean } | null) => ({
    label,
    count: c ? c.count : null,
    small: !!c?.small,
  });
  return [
    row("Screened", f.screened),
    row("Enrolled", f.enrolled),
    row("Completed", f.completed),
    row("Withdrew", f.withdrawn),
    row("Ineligible", f.ineligible),
    ...f.excluded.map((e) => row(`Excluded: ${e.reason}`, e)),
    ...(f.analysed ? [row(f.set ? `Analysed (${f.set})` : "Analysed", f.analysed)] : []),
  ];
}

/** A table Word accepts when pasted. Counts only: no codes, no rows of people. */
export function flowTableHtml(f: Flow): string {
  const rows = flowRows(f)
    .map(
      (r) =>
        `<tr><td>${esc(r.label)}</td><td style="text-align:right">${r.count ?? ""}${
          r.small ? " *" : ""
        }</td></tr>`,
    )
    .join("");
  const note = f.warning ? `<p>* Fewer than ${f.small_cell_limit}. ${esc(f.warning)}</p>` : "";
  return `<table border="1" cellspacing="0" cellpadding="4"><thead><tr><th>Stage</th><th>n</th></tr></thead><tbody>${rows}</tbody></table>${note}`;
}

/** A simple boxes-and-arrows diagram as SVG text. */
export function flowSvg(f: Flow): string {
  const rows = flowRows(f);
  const w = 360;
  const h = rows.length * 52 + 16;
  const boxes = rows
    .map((r, i) => {
      const y = 8 + i * 52;
      return (
        `<rect x="8" y="${y}" width="${w - 16}" height="40" rx="8" fill="#f4f4f5" stroke="#a1a1aa"/>` +
        `<text x="20" y="${y + 25}" font-family="Inter, sans-serif" font-size="14" fill="#18181b">${esc(
          r.label,
        )}</text>` +
        `<text x="${w - 20}" y="${y + 25}" text-anchor="end" font-family="Inter, sans-serif" font-size="14" font-weight="600" fill="#18181b">${r.count ?? ""}${
          r.small ? "*" : ""
        }</text>` +
        (i < rows.length - 1
          ? `<path d="M${w / 2} ${y + 40} v12" stroke="#71717a" stroke-width="1.5"/>`
          : "")
      );
    })
    .join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="Participant flow"><rect width="100%" height="100%" fill="#ffffff"/>${boxes}</svg>`;
}

export function download(name: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function svgToPng(svg: string): Promise<Blob> {
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  const img = new Image();
  await new Promise<void>((ok, bad) => {
    img.onload = () => ok();
    img.onerror = () => bad(new Error("image"));
    img.src = url;
  });
  const canvas = document.createElement("canvas");
  canvas.width = img.width * 2;
  canvas.height = img.height * 2;
  const ctx = canvas.getContext("2d")!;
  ctx.scale(2, 2);
  ctx.drawImage(img, 0, 0);
  URL.revokeObjectURL(url);
  return await new Promise((ok, bad) =>
    canvas.toBlob((b) => (b ? ok(b) : bad(new Error("png"))), "image/png"),
  );
}
