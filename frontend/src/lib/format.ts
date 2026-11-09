export const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

/** Full date and time in the user's locale, for hover text. */
export const fullDate = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "long", timeStyle: "short" });

/** YYYY-MM-DD in the user's own timezone (`toISOString` would give the date in UTC). */
export const localDateISO = (d = new Date()) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/** "1 day" or "2 days". Pass the plural form when it is irregular. */
export const plural = (n: number, singular: string, pluralForm = `${singular}s`) =>
  `${n} ${Math.abs(n) === 1 ? singular : pluralForm}`;

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 31536000],
  ["month", 2592000],
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
];

/** "in 25 days", "3 hours ago", "just now", in the browser's locale. */
export function relativeTime(iso: string, now = Date.now()): string {
  const secs = (new Date(iso).getTime() - now) / 1000;
  if (Math.abs(secs) < 60) return "just now";
  const [unit, size] = UNITS.find(([, s]) => Math.abs(secs) >= s) ?? UNITS[UNITS.length - 1]!;
  return new Intl.RelativeTimeFormat(undefined, { numeric: "always" }).format(
    Math.round(secs / size),
    unit,
  );
}
