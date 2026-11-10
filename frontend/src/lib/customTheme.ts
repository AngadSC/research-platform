export interface Palette {
  background: string;
  text: string;
  accent: string;
}
export interface CustomTheme extends Palette {
  id: string;
  name: string;
}

export const MAX_CUSTOM_THEMES = 10;
/** Same number as MIN_CONTRAST in core/serializers.py. 6:1 on the plain background keeps text at
 * 4.5:1 (WCAG AA) on the tinted panels made from it; customTheme.test.ts checks that. */
export const MIN_CONTRAST = 6;
const AA = 4.5;
const WHITE = "#ffffff";
const NEAR_BLACK = "#09090b";

const channels = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));

function luminance(hex: string) {
  const [r = 0, g = 0, b = 0] = channels(hex).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string) {
  const [high = 0, low = 0] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

export function mix(from: string, to: string, amount: number) {
  const target = channels(to);
  const out = channels(from).map((v, i) => Math.round(v + ((target[i] ?? 0) - v) * amount));
  return `#${out.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

export const isDarkPalette = (p: Palette) =>
  contrast(p.background, WHITE) > contrast(p.background, NEAR_BLACK);
const textOn = (fill: string) =>
  contrast(fill, WHITE) >= contrast(fill, NEAR_BLACK) ? WHITE : NEAR_BLACK;

/** Plain-English reasons this palette is hard to read; empty when it is fine. */
export function paletteProblems(p: Palette): string[] {
  const out: string[] = [];
  if (contrast(p.text, p.background) < MIN_CONTRAST)
    out.push("The text is too hard to read on this background. Pick colours further apart.");
  if (contrast(p.accent, p.background) < MIN_CONTRAST)
    out.push("The accent colour is too hard to read on this background. Pick a stronger colour.");
  return out;
}

/** The app's colour tokens for a palette. Status fills keep their own light or dark values. */
export function paletteVars(palette: Palette): Record<string, string> {
  const { background, text, accent } = palette;
  const surface = mix(background, text, 0.06);
  const mutedText =
    [0.35, 0.3, 0.25, 0.2, 0.15, 0.1, 0.05]
      .map((amount) => mix(text, background, amount))
      .find((c) => contrast(c, background) >= AA && contrast(c, surface) >= AA) ?? text;
  const baseDanger = isDarkPalette(palette) ? "#f87171" : "#b91c1c";
  const danger = contrast(baseDanger, background) >= AA ? baseDanger : text;
  return {
    "--background": background,
    "--foreground": text,
    "--card": background,
    "--card-foreground": text,
    "--popover": background,
    "--popover-foreground": text,
    "--primary": accent,
    "--primary-foreground": textOn(accent),
    "--secondary": surface,
    "--secondary-foreground": text,
    "--muted": surface,
    "--muted-foreground": mutedText,
    "--accent": surface,
    "--accent-foreground": text,
    "--border": mix(background, text, 0.15),
    "--input": mix(background, text, 0.25),
    "--ring": accent,
    "--sidebar": mix(background, text, 0.03),
    "--danger": danger,
    "--danger-foreground": textOn(danger),
    // ponytail: status text follows the theme's text colour, since a fixed green or amber can
    // fail on a mid-tone background. Pick per-colour shades if people miss the hue.
    "--danger-text": text,
    "--success-text": text,
    "--warning-text": text,
    "--info-text": text,
  };
}

export const PALETTE_VARS = Object.keys(
  paletteVars({ background: WHITE, text: NEAR_BLACK, accent: NEAR_BLACK }),
);
