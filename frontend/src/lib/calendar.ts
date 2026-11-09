import type { CalendarItem } from "@/lib/api-types";

/** Local dates for the weeks (Sunday first) that contain the month. `month` is 0-based. */
export function monthGrid(year: number, month: number): Date[] {
  const offset = new Date(year, month, 1).getDay();
  const days = new Date(year, month + 1, 0).getDate();
  const count = Math.ceil((offset + days) / 7) * 7;
  return Array.from({ length: count }, (_, i) => new Date(year, month, 1 - offset + i));
}

/** What falls on a YYYY-MM-DD day; a multi-day event is on every one of its days. */
export const itemsOn = (items: CalendarItem[], iso: string) =>
  items.filter((i) => i.date <= iso && (i.end_date ?? i.date) >= iso);

/** Where an item lives. Null for lab events: they open in place. */
export function calendarHref(labId: string, item: CalendarItem): string | null {
  const lab = `/labs/${labId}`;
  const project = `${lab}/projects/${item.project_id}`;
  switch (item.kind) {
    case "deadline":
      return `${project}/overview`;
    case "task":
      return `${project}/tasks?task=${item.id}`;
    case "funding":
      return `${project}/workflow/funding`;
    case "inventory":
      return `${lab}/inventory`;
    case "ethics":
      return `${lab}/ethics/${item.id}`;
    case "event":
      return null;
  }
}
