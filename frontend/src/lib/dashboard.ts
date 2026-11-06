import type { DashProject } from "@/hooks/dashboard";

/** A date-only string ("2026-11-20") as a local date, so it never slips a day across time zones. */
export const localDate = (d: string) => {
  const [y, m, day] = d.split("-").map(Number) as [number, number, number];
  return new Date(y, m - 1, day);
};
export const shortDate = (d: string) =>
  localDate(d).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
export const daysFromToday = (d: string, now = new Date()) =>
  Math.round(
    (localDate(d).getTime() -
      new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()) /
      86_400_000,
  );

/** "3 days overdue", "due today", "in 5 days". */
export function dueText(days: number, noun = "overdue"): string {
  if (days < 0) return `${-days} ${-days === 1 ? "day" : "days"} ${noun}`;
  if (days === 0) return "today";
  return `in ${days} ${days === 1 ? "day" : "days"}`;
}

export const HEALTH_LABEL = { red: "At risk", amber: "Watch", green: "Healthy" } as const;
const HEALTH_RANK = { red: 0, amber: 1, green: 2 } as const;
const PRIORITY_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 };

export type SortKey =
  | "name"
  | "status"
  | "health"
  | "open"
  | "overdue"
  | "in_progress"
  | "deadline"
  | "edited"
  | "funding";

const FAR = "9999-12-31";
/** Sort value per column. Missing dates sort last when ascending. */
export function sortValue(p: DashProject, key: SortKey): string | number {
  switch (key) {
    case "name":
      return p.name.toLowerCase();
    case "status":
      return p.status;
    case "health":
      return HEALTH_RANK[p.health];
    case "open":
      return p.open_tasks;
    case "overdue":
      return p.overdue_tasks;
    case "in_progress":
      return p.in_progress_tasks;
    case "deadline":
      return p.next_deadline
        ? `${p.next_deadline.due_date}-${PRIORITY_RANK[p.next_deadline.priority] ?? 3}`
        : FAR;
    case "edited":
      return p.last_activity_at ?? "";
    case "funding":
      return p.funding_end_date ?? FAR;
  }
}

export function sortProjects(
  rows: DashProject[],
  key: SortKey,
  dir: "asc" | "desc",
): DashProject[] {
  const sign = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = sortValue(a, key);
    const y = sortValue(b, key);
    return (x < y ? -1 : x > y ? 1 : a.name.localeCompare(b.name)) * sign;
  });
}
