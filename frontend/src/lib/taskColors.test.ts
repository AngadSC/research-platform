import { describe, expect, it } from "vitest";
import { contrast, TASK_TONES } from "@/lib/taskColors";

describe("task colours (D144)", () => {
  it("measures contrast like WCAG", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 0);
    expect(contrast("#777777", "#ffffff")).toBeLessThan(4.5);
  });

  it.each(Object.entries(TASK_TONES))("%s: every text pair is at least AA (4.5:1)", (_s, t) => {
    expect(contrast(t.onStrong, t.strong)).toBeGreaterThanOrEqual(4.5);
    for (const bg of [t.column, t.card])
      for (const fg of [t.text, t.muted]) expect(contrast(fg, bg)).toBeGreaterThanOrEqual(4.5);
  });

  it("uses yellow, orange and green", () => {
    const hue = (hex: string) => {
      const n = parseInt(hex.slice(1), 16);
      const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => v / 255) as [
        number,
        number,
        number,
      ];
      const max = Math.max(r, g, b);
      const d = max - Math.min(r, g, b);
      const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
      return (h * 60 + 360) % 360;
    };
    expect(hue(TASK_TONES.todo.strong)).toBeGreaterThan(40);
    expect(hue(TASK_TONES.todo.strong)).toBeLessThan(60);
    expect(hue(TASK_TONES.in_progress.strong)).toBeGreaterThan(20);
    expect(hue(TASK_TONES.in_progress.strong)).toBeLessThan(35);
    expect(hue(TASK_TONES.done.strong)).toBeGreaterThan(120);
    expect(hue(TASK_TONES.done.strong)).toBeLessThan(160);
  });
});
