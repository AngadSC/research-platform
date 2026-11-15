import css from "@/index.css?raw";
import { describe, expect, it } from "vitest";

/**
 * Text contrast on glass (WCAG AA: 4.5:1 for body text, 3:1 for large text and icons), measured
 * over a worst-case backdrop in both themes. If a pair fails, raise the surface's opacity in
 * index.css rather than the blur.
 */

/** Every `selector { … }` block in the file, joined: the tokens are spread over several. */
const block = (selector: string) => {
  let out = "";
  let from = 0;
  for (;;) {
    const start = css.indexOf(`\n${selector} {`, from);
    if (start < 0) return out;
    const end = css.indexOf("\n}\n", start);
    out += css.slice(start, end);
    from = end;
  }
};
const LIGHT = block(":root");
const DARK = block(".dark");

const hex = (src: string, name: string) => {
  const m = new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})`).exec(src);
  if (!m) throw new Error(`no ${name}`);
  return m[1]!;
};
const percent = (src: string, name: string) => {
  const m = new RegExp(`${name}:\\s*color-mix\\(in srgb, var\\(--card\\) (\\d+)%`).exec(src);
  if (!m) throw new Error(`no ${name}`);
  return Number(m[1]) / 100;
};
const rgb = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const mix = (top: number[], bottom: number[], alpha: number) =>
  top.map((c, i) => c * alpha + bottom[i]! * (1 - alpha));
const lum = (c: number[]) => {
  const [r, g, b] = c.map((v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
};
const ratio = (a: number[], b: number[]) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
};

// The worst thing a translucent surface can sit over: the strongest mesh tint under a very
// different tone, for each theme.
const WORST = { light: rgb("#8b8bd8"), dark: rgb("#3d3a9e") };

describe.each([
  ["light", LIGHT, WORST.light],
  ["dark", DARK, WORST.dark],
] as const)("%s theme", (name, src, backdrop) => {
  const fallback = name === "dark" ? LIGHT : src; // colours the dark block does not restate
  const get = (n: string) => {
    try {
      return rgb(hex(src, n));
    } catch {
      return rgb(hex(fallback, n));
    }
  };
  const card = get("--card");
  const surface = (token: string) => mix(card, backdrop, percent(src, token));

  it.each(["--glass-bg", "--glass-bg-strong", "--glass-bg-solid"])(
    "text stays readable on %s",
    (token) => {
      const bg = surface(token);
      // Body text on any glass surface. A translucent surface must not be used for body text
      // below this, and the chrome that uses --glass-bg only carries labels this contrasty.
      const need = token === "--glass-bg" ? 4.5 : 4.5;
      expect(ratio(get("--foreground"), bg)).toBeGreaterThanOrEqual(need);
    },
  );

  it("secondary text is readable on the strong and solid surfaces", () => {
    for (const token of ["--glass-bg-strong", "--glass-bg-solid"])
      expect(ratio(get("--muted-foreground"), surface(token))).toBeGreaterThanOrEqual(4.5);
  });

  it("primary button text passes on both ends of its gradient", () => {
    const fg = get("--primary-foreground");
    expect(ratio(fg, get("--primary"))).toBeGreaterThanOrEqual(4.5);
    expect(ratio(fg, get("--primary-lift"))).toBeGreaterThanOrEqual(4.5);
  });

  it("status text passes on the strong glass surface", () => {
    for (const n of ["--success-text", "--danger-text", "--info-text", "--warning-text"])
      expect(ratio(get(n), surface("--glass-bg-strong"))).toBeGreaterThanOrEqual(4.5);
  });

  it("the focus ring is visible against glass (3:1)", () => {
    expect(ratio(get("--ring"), surface("--glass-bg-strong"))).toBeGreaterThanOrEqual(3);
  });
});

describe("fallbacks exist", () => {
  it.each([
    "prefers-reduced-transparency",
    "forced-colors",
    "prefers-reduced-motion",
    '[data-glass="reduced"]',
    "@supports not",
  ])("handles %s", (needle) => {
    expect(css).toContain(needle);
  });
});
