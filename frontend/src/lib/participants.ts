import {
  Ban,
  CircleAlert,
  CircleCheck,
  CircleDashed,
  Eye,
  Hourglass,
  Minus,
  type LucideIcon,
} from "lucide-react";
import type { CellStatus, RegistryCell } from "@/lib/api-types";

export interface StatusInfo {
  value: CellStatus;
  label: string;
  /** One line for tooltips and the panel. */
  hint: string;
  icon: LucideIcon;
  /** Tinted chip classes. Every status also has its own icon and label: never colour alone. */
  tone: string;
  /** Keyboard shortcut in the grid. */
  key: string;
  needsReason: boolean;
}

export const STATUSES: StatusInfo[] = [
  {
    value: "not_started",
    label: "Not started",
    hint: "Expected, but no work has begun.",
    icon: CircleDashed,
    tone: "bg-muted text-muted-foreground",
    key: "1",
    needsReason: false,
  },
  {
    value: "in_progress",
    label: "In progress",
    hint: "Being collected, transcribed, translated or scored.",
    icon: Hourglass,
    tone: "bg-info/15 text-info-text",
    key: "2",
    needsReason: false,
  },
  {
    value: "needs_review",
    label: "Needs review",
    hint: "Done by one person, waiting for a second check.",
    icon: Eye,
    tone: "bg-warning/20 text-warning-text",
    key: "3",
    needsReason: false,
  },
  {
    value: "complete",
    label: "Complete",
    hint: "Verified and linked.",
    icon: CircleCheck,
    tone: "bg-success/15 text-success-text",
    key: "4",
    needsReason: false,
  },
  {
    value: "missing",
    label: "Missing",
    hint: "Expected, and will not exist unless someone acts. Needs a reason.",
    icon: CircleAlert,
    tone: "bg-danger/15 text-danger-text",
    key: "5",
    needsReason: true,
  },
  {
    value: "not_applicable",
    label: "Not applicable",
    hint: "Does not apply to this participant. Needs a reason.",
    icon: Minus,
    tone: "border border-dashed border-muted-foreground/50 text-muted-foreground",
    key: "6",
    needsReason: true,
  },
  {
    value: "excluded",
    label: "Excluded",
    hint: "Present but not usable. Needs a reason.",
    icon: Ban,
    tone: "bg-danger/10 text-danger-text [background-image:repeating-linear-gradient(135deg,transparent,transparent_4px,rgb(0_0_0/0.06)_4px,rgb(0_0_0/0.06)_8px)]",
    key: "7",
    needsReason: true,
  },
];

export const STATUS = Object.fromEntries(STATUSES.map((s) => [s.value, s])) as Record<
  CellStatus,
  StatusInfo
>;

export const REASON_KIND: Partial<Record<CellStatus, string>> = {
  missing: "missing",
  not_applicable: "not_applicable",
  excluded: "excluded",
};

/** A cell that has never been touched reads as Not started. */
export const statusOf = (cell?: RegistryCell): CellStatus => cell?.status ?? "not_started";

/** Cells that count toward "percent complete": everything except Not applicable and Excluded. */
export function completeness(cells: (RegistryCell | undefined)[]) {
  let counted = 0;
  let done = 0;
  for (const c of cells) {
    const s = statusOf(c);
    if (s === "not_applicable" || s === "excluded") continue;
    counted += 1;
    if (s === "complete") done += 1;
  }
  return { counted, done, percent: counted ? Math.round((done / counted) * 100) : 0 };
}

export const isOverdue = (cell: RegistryCell | undefined, today: string) =>
  !!cell?.due_date && cell.due_date < today && statusOf(cell) !== "complete";

/** Split pasted text into codes (spaces, commas, semicolons, new lines). */
export function parseCodes(text: string): string[] {
  const seen = new Set<string>();
  for (const part of text.split(/[\s,;]+/)) if (part.trim()) seen.add(part.trim());
  return [...seen];
}

export const CATEGORIES = [
  ["session", "Session"],
  ["transcript", "Transcript"],
  ["translation", "Translation"],
  ["scoring", "Scoring"],
  ["questionnaire", "Questionnaire"],
  ["consent", "Consent"],
  ["other", "Other"],
] as const;

export const ENROLMENT = [
  ["screened", "Screened"],
  ["enrolled", "Enrolled"],
  ["active", "Active"],
  ["completed", "Completed"],
  ["withdrawn", "Withdrawn"],
  ["ineligible", "Ineligible"],
] as const;

export const CODES_ONLY = "Coded IDs only. Do not enter names or contact details.";
