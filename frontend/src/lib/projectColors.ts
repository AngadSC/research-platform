import type { CSSProperties } from "react";

/** Same names and order as `ProjectColor` in backend/projects/models.py. */
export const PROJECT_COLORS = [
  "blue",
  "orange",
  "green",
  "pink",
  "teal",
  "yellow",
  "violet",
  "red",
  "lime",
  "brown",
] as const;

/** Sets `--project` to a project's colour for this element and its children (themed in index.css). */
export const projectColorStyle = (color: string) =>
  ({ "--project": `var(--project-${color})` }) as CSSProperties;
