import { describe, expect, it } from "vitest";
import { contrast, MIN_CONTRAST, mix, paletteProblems, paletteVars } from "@/lib/customTheme";

const STEPS = [0, 64, 128, 192, 255];
const hex = (...rgb: number[]) => `#${rgb.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
const COLOURS = STEPS.flatMap((r) => STEPS.flatMap((g) => STEPS.map((b) => hex(r, g, b))));

describe("custom themes", () => {
  it("measures contrast the WCAG way", () => {
    expect(contrast("#ffffff", "#000000")).toBeCloseTo(21);
    expect(contrast("#4f46e5", "#ffffff")).toBeCloseTo(6.29, 1);
  });

  it("flags palettes that are hard to read", () => {
    const fine = { background: "#ffffff", text: "#18181b", accent: "#4f46e5" };
    expect(paletteProblems(fine)).toEqual([]);
    expect(paletteProblems({ ...fine, text: "#aaaaaa" })).toHaveLength(1);
    expect(paletteProblems({ ...fine, accent: "#ffff00" })).toHaveLength(1);
  });

  it("keeps every text colour readable on every surface of an accepted palette", () => {
    let checked = 0;
    let worst = Infinity;
    for (const background of COLOURS)
      for (const text of COLOURS) {
        if (contrast(text, background) < MIN_CONTRAST) continue;
        const accent = text; // the accent passes the same rule as the text
        const v = paletteVars({ background, text, accent });
        const muted = v["--muted-foreground"] ?? "";
        checked += 1;
        for (const surface of [background, v["--muted"] ?? "", v["--sidebar"] ?? ""])
          worst = Math.min(worst, contrast(text, surface), contrast(muted, surface));
        worst = Math.min(
          worst,
          // the active tab (on the page) and the active sidebar link
          contrast(accent, mix(background, accent, 0.1)),
          contrast(accent, mix(v["--sidebar"] ?? "", accent, 0.1)),
          contrast(v["--primary-foreground"] ?? "", accent),
          contrast(v["--danger-foreground"] ?? "", v["--danger"] ?? ""),
          contrast(v["--danger"] ?? "", background),
        );
      }
    expect(checked).toBeGreaterThan(1000);
    expect(worst).toBeGreaterThanOrEqual(4.5);
  });
});
