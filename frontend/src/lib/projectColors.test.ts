import { describe, expect, it } from "vitest";
import css from "@/index.css?raw";
import { PROJECT_COLORS } from "./projectColors";
import { contrast } from "./taskColors";

const [light = "", dark = ""] = css.split(".dark {");
const token = (block: string, name: string) => {
  const hit = block.match(new RegExp(`--${name}: (#[0-9a-f]{6})`));
  if (!hit) throw new Error(`no --${name}`);
  return hit[1] as string;
};
/** `color-mix(in srgb, top pct%, bottom)`, as the sidebar's hover tint does it. */
const mix = (top: string, bottom: string, pct: number) => {
  const part = (hex: string, i: number) => parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16);
  const blended = [0, 1, 2].map((i) =>
    Math.round((part(top, i) * pct + part(bottom, i) * (100 - pct)) / 100),
  );
  return `#${blended.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
};

describe.each([
  ["light", light],
  ["dark", dark],
])("project colours in the %s theme", (_, block) => {
  const sidebar = token(block, "sidebar");
  it.each(PROJECT_COLORS)("%s is visible, and text on its hover tint passes AA", (color) => {
    const value = token(block, `project-${color}`);
    expect(contrast(value, sidebar)).toBeGreaterThanOrEqual(3);
    for (const text of ["foreground", "muted-foreground"])
      expect(contrast(token(block, text), mix(value, sidebar, 18))).toBeGreaterThanOrEqual(4.5);
  });
});
