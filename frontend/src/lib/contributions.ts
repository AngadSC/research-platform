/** Pure helpers for the contribution graph, kept apart so they are easy to test. */

export type KindCounts = {
  documents: number;
  files: number;
  tasks: number;
  task_updates: number;
  chat: number;
  records: number;
};

export const KIND_LABELS: Record<keyof KindCounts, [string, string]> = {
  documents: ["document edited", "documents edited"],
  files: ["file uploaded", "files uploaded"],
  tasks: ["task created", "tasks created"],
  task_updates: ["task update", "task updates"],
  chat: ["chat message", "chat messages"],
  records: ["research record", "research records"],
};

export type Cell = { date: string; count: number; level: 0 | 1 | 2 | 3 | 4; future: boolean };

/** "2026-11-09" as a local date (never shifted by the time zone, unlike `new Date(iso)`). */
export function parseDay(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y!, m! - 1, d!);
}

export function isoDay(d: Date): string {
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

/** Shade 1-4 by quarter of the busiest day, so one huge day does not wash out the rest. */
export function level(count: number, max: number): Cell["level"] {
  if (count <= 0 || max <= 0) return 0;
  return Math.min(4, Math.max(1, Math.ceil((count / max) * 4))) as Cell["level"];
}

/**
 * Columns of seven days (Sunday to Saturday) from `start` (a Sunday) through the week holding
 * `end`. Days after `end` are marked `future` and drawn empty, as GitHub does.
 */
export function buildWeeks(start: string, end: string, days: { date: string; count: number }[]) {
  const counts = new Map(days.map((d) => [d.date, d.count]));
  const max = Math.max(0, ...days.map((d) => d.count));
  const last = parseDay(end);
  const weeks: Cell[][] = [];
  const cursor = parseDay(start);
  while (cursor <= last) {
    const week: Cell[] = [];
    for (let i = 0; i < 7; i++) {
      const date = isoDay(cursor);
      const count = counts.get(date) ?? 0;
      week.push({ date, count, level: level(count, max), future: cursor > last });
      cursor.setDate(cursor.getDate() + 1);
    }
    weeks.push(week);
  }
  return weeks;
}

/** A month name over the first column of each month; the first is dropped if it is cramped. */
export function monthLabels(weeks: Cell[][]): { index: number; label: string }[] {
  const out: { index: number; label: string }[] = [];
  let prev = -1;
  weeks.forEach((week, index) => {
    const month = parseDay(week[0]!.date).getMonth();
    if (month !== prev) {
      out.push({
        index,
        label: parseDay(week[0]!.date).toLocaleDateString(undefined, { month: "short" }),
      });
      prev = month;
    }
  });
  if (out.length > 1 && out[1]!.index - out[0]!.index < 3) out.shift();
  return out;
}

/** "Mon, Nov 9, 2026". */
export const dayName = (iso: string) =>
  parseDay(iso).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
