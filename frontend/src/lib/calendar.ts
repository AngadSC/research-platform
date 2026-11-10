import type { CalendarItem } from "@/lib/api-types";
import { localDateISO } from "@/lib/format";

/** Local dates for the weeks (Sunday first) that contain the month. `month` is 0-based. */
export function monthGrid(year: number, month: number): Date[] {
  const offset = new Date(year, month, 1).getDay();
  const days = new Date(year, month + 1, 0).getDate();
  const count = Math.ceil((offset + days) / 7) * 7;
  return Array.from({ length: count }, (_, i) => new Date(year, month, 1 - offset + i));
}

/** A meeting belongs on the viewer's own local day, not the UTC day the server sends. */
const startDay = (i: CalendarItem) => (i.starts_at ? localDateISO(new Date(i.starts_at)) : i.date);

/** What falls on a YYYY-MM-DD day; a multi-day event is on every one of its days. */
export const itemsOn = (items: CalendarItem[], iso: string) =>
  items.filter((i) => startDay(i) <= iso && (i.end_date ?? startDay(i)) >= iso);

/** The value a `datetime-local` input wants, in the viewer's own time. */
export function toLocalInput(d: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${localDateISO(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Where an item lives. Null for lab events and meetings: they open in place. */
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
    case "meeting":
      return null;
  }
}
