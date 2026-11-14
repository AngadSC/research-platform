import { localDateISO } from "@/lib/format";

export interface CaptureProject {
  id: string;
  name: string;
}

export interface Captured {
  title: string;
  /** YYYY-MM-DD, or null when no date was written. */
  due: string | null;
  /** The words that were read as the date, for showing back to the person. */
  dueWords: string;
  project: CaptureProject | null;
  /** What was written after `#`, even when it matched nothing. */
  projectQuery: string;
}

const DAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];
const DAY_ALIASES: Record<string, number> = {
  sun: 0,
  mon: 1,
  tue: 2,
  tues: 2,
  wed: 3,
  weds: 3,
  thu: 4,
  thur: 4,
  thurs: 4,
  fri: 5,
  sat: 6,
};
const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
const addDays = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const dayIndex = (word: string) => {
  const w = word.toLowerCase();
  const full = DAYS.indexOf(w);
  return full >= 0 ? full : (DAY_ALIASES[w] ?? -1);
};

/** "Friday" is the next Friday after today; "this Friday" may be today. */
function nextWeekday(from: Date, target: number, allowToday: boolean): Date {
  let diff = (target - from.getDay() + 7) % 7;
  if (diff === 0 && !allowToday) diff = 7;
  return addDays(from, diff);
}

interface Found {
  date: Date;
  start: number;
  end: number;
}

/** The first date phrase in `text` (indexes into it), or null. Understands today, tomorrow,
 * weekdays ("fri", "next monday", "this friday"), "in 3 days/weeks", "next week", "Dec 5",
 * "5 Dec" and 2026-12-05. */
function findDate(text: string, now: Date): Found | null {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const patterns: [RegExp, (m: RegExpExecArray) => Date | null][] = [
    [/\b(\d{4})-(\d{2})-(\d{2})\b/i, (m) => new Date(+m[1]!, +m[2]! - 1, +m[3]!)],
    [/\b(today|tonight)\b/i, () => today],
    [/\b(tomorrow|tmrw|tmr)\b/i, () => addDays(today, 1)],
    [/\bnext\s+week\b/i, () => nextWeekday(today, 1, false)],
    [
      /\bin\s+(\d{1,2})\s+(day|days|week|weeks)\b/i,
      (m) => addDays(today, +m[1]! * (m[2]!.startsWith("week") ? 7 : 1)),
    ],
    [
      /\b(?:(next|this)\s+)?(sunday|monday|tuesday|wednesday|thursday|friday|saturday|sun|mon|tues?|weds?|thu|thur|thurs|fri|sat)\b/i,
      (m) => nextWeekday(today, dayIndex(m[2]!), (m[1] ?? "").toLowerCase() === "this"),
    ],
    [
      /\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b/i,
      (m) => monthDay(today, m[1]!, +m[2]!),
    ],
    [
      /\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b/i,
      (m) => monthDay(today, m[2]!, +m[1]!),
    ],
  ];
  let best: Found | null = null;
  for (const [re, make] of patterns) {
    const m = re.exec(text);
    if (!m) continue;
    const date = make(m);
    if (!date || (best && m.index >= best.start)) continue;
    best = { date, start: m.index, end: m.index + m[0].length };
  }
  return best;
}

function monthDay(today: Date, mon: string, day: number): Date | null {
  const month = MONTHS.indexOf(mon.slice(0, 3).toLowerCase());
  if (month < 0 || day < 1 || day > 31) return null;
  let d = new Date(today.getFullYear(), month, day);
  if (d.getMonth() !== month) return null; // 31 Feb and the like
  if (d < today) d = new Date(today.getFullYear() + 1, month, day);
  return d;
}

/** One line to a task: "email Dr. Bhalloo Friday #paper2" is the title "email Dr. Bhalloo", due
 * the coming Friday, in the project whose name best matches "paper2". */
export function parseCapture(
  input: string,
  projects: CaptureProject[],
  now = new Date(),
): Captured {
  let text = input;
  let projectQuery = "";
  const tag = /(^|\s)#([\w-]+)/.exec(text);
  if (tag) {
    projectQuery = tag[2]!;
    text = text.slice(0, tag.index) + " " + text.slice(tag.index + tag[0].length);
  }
  let due: string | null = null;
  let dueWords = "";
  const found = findDate(text, now);
  if (found) {
    due = localDateISO(found.date);
    dueWords = text.slice(found.start, found.end);
    // "by Friday", "due Friday", "on Friday": the little word belongs to the date.
    const before = text.slice(0, found.start).replace(/\s*\b(by|due|on|before)\s*$/i, "");
    text = `${before} ${text.slice(found.end)}`;
  }
  const title = text.replace(/\s+/g, " ").trim();
  return { title, due, dueWords, project: matchProject(projectQuery, projects), projectQuery };
}

/** The project `#tag` means: same name, else one that starts with it, else one that has it
 * inside, ignoring case, spaces and punctuation. Nothing when two fit equally. */
export function matchProject(query: string, projects: CaptureProject[]): CaptureProject | null {
  const q = norm(query);
  if (!q) return null;
  const tiers = [
    projects.filter((p) => norm(p.name) === q),
    projects.filter((p) => norm(p.name).startsWith(q)),
    projects.filter((p) => norm(p.name).includes(q)),
  ];
  for (const tier of tiers) if (tier.length) return tier.length === 1 ? tier[0]! : null;
  return null;
}
