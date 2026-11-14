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
