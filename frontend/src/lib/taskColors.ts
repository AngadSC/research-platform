import type { TaskStatus } from "@/lib/api-types";

/** Board colours (D144): To do yellow, In progress orange, Done green. Fixed light surfaces with
 * dark text in both themes (white on the green chip), because the theme's semantic tokens have no
 * orange. Every text/background pair is at least WCAG AA 4.5:1; taskColors.test.ts checks them. */
export interface TaskTone {
  /** Column background. */
  column: string;
  /** Card background. */
  card: string;
  /** Strong stripe and header chip. */
  strong: string;
  /** Text on the chip. */
  onStrong: string;
  /** Text on column and card. */
  text: string;
  /** Secondary text on column and card. */
  muted: string;
}

export const TASK_TONES: Record<TaskStatus, TaskTone> = {
  todo: {
    column: "#fef08a",
    card: "#fef9c3",
    strong: "#facc15",
    onStrong: "#1c1917",
    text: "#1c1917",
    muted: "#44403c",
  },
  in_progress: {
    column: "#fed7aa",
    card: "#ffedd5",
    strong: "#fb923c",
    onStrong: "#1c1917",
    text: "#1c1917",
    muted: "#44403c",
  },
  done: {
    column: "#bbf7d0",
    card: "#dcfce7",
    strong: "#15803d",
    onStrong: "#ffffff",
    text: "#14291d",
    muted: "#3f3f46",
  },
};

const channel = (v: number) => {
  const c = v / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
};
const luminance = (hex: string) => {
  const n = parseInt(hex.slice(1), 16);
  return (
    0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255)
  );
};

/** WCAG contrast ratio of two #rrggbb colours. */
export function contrast(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}
