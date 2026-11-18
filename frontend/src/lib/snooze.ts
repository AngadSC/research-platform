import { localDateISO } from "@/lib/format";

/** `iso` plus `n` days, as YYYY-MM-DD. */
export function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + n);
  return localDateISO(d);
}

/** The coming Monday: from a Monday it is the Monday after. */
export function nextMonday(todayIso: string): string {
  const day = new Date(`${todayIso}T00:00:00`).getDay();
  return addDays(todayIso, (8 - day) % 7 || 7);
}

/** The moment a date-only snooze ends: the start of that day, here. */
export const dayStart = (iso: string) => new Date(`${iso}T00:00:00`).toISOString();

/** Three hours from `now`, for "Later today". */
export const inThreeHours = (now = new Date()) =>
  new Date(now.getTime() + 3 * 3600_000).toISOString();

/** True while a task is resting: its snooze has not run out yet. */
export const isSnoozed = (until: string | null | undefined, now = new Date()) =>
  !!until && new Date(until) > now;

/** "3:40 PM" when it wakes today, else "Mon, 16 Nov". */
export function snoozeEnds(until: string, now = new Date()): string {
  const d = new Date(until);
  return localDateISO(d) === localDateISO(now)
    ? d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
    : d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}
