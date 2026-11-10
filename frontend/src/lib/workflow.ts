import type { BadgeVariant } from "@/components/ui/badge";
import type { Kind } from "@/lib/research";

/** D132: the Workflow sub-tabs, in display order. */
export const SECTIONS = [
  ["funding", "Funding"],
  ["ethics", "Ethics"],
  ["participants", "Participants"],
  ["data", "Data"],
  ["analysis", "Analysis"],
  ["manuscript", "Manuscript"],
  ["review", "Review"],
] as const;
export type Section = (typeof SECTIONS)[number][0];

/** What finishes each stage, shown as the "do this next" line. */
export const NEXT_STEP: Record<Section, string> = {
  funding: "Record the grant or award that pays for this project.",
  ethics: "Link an ethics approval that is still valid.",
  participants: "Record how many people you have enrolled.",
  data: "Add a record of the dataset you collected.",
  analysis: "Add a result from your analysis.",
  manuscript: "Link your manuscript once it has been submitted.",
  review: "Get every review item approved.",
};

export const EXTERNAL_TYPES = [
  ["poster", "Poster"],
  ["presentation", "Presentation"],
  ["conference", "Conference"],
  ["other", "Other"],
] as const;
export type ResearchSection = "data" | "analysis" | "manuscript" | "review";

/** Which research records each section lists (decisions sit under Review, D132). */
export const SECTION_KINDS: Record<ResearchSection, Kind[]> = {
  data: ["datasets"],
  analysis: ["analyses", "results"],
  manuscript: ["manuscripts"],
  review: ["decisions"],
};
export const sectionOf = (kind: Kind): ResearchSection =>
  (Object.keys(SECTION_KINDS) as ResearchSection[]).find((s) => SECTION_KINDS[s].includes(kind))!;

/** `/labs/x/projects/y/workflow/<section>/<kind>[/<id>|/new]` for a research record or form. */
export const recordPath = (projectBase: string, kind: Kind, id?: string) =>
  `${projectBase}/workflow/${sectionOf(kind)}/${kind}${id ? `/${id}` : ""}`;

export const FUNDING_STATUSES = [
  ["applied", "Applied"],
  ["awarded", "Awarded"],
  ["active", "Active"],
  ["closed", "Closed"],
  ["declined", "Declined"],
] as const;
export const REVIEW_STATUSES = [
  ["requested", "Requested"],
  ["in_review", "In review"],
  ["changes_requested", "Changes requested"],
  ["approved", "Approved"],
] as const;
export const RECRUITMENT_STATUSES = [
  ["screened", "Screened"],
  ["enrolled", "Enrolled"],
  ["withdrawn", "Withdrawn"],
  ["completed", "Completed"],
] as const;
export const PRIORITIES = [
  ["high", "High"],
  ["medium", "Medium"],
  ["low", "Low"],
] as const;

/** Semantic badge tones (red, amber and green come from the colour tokens). */
export const PRIORITY_TONE: Record<string, BadgeVariant> = {
  high: "destructive",
  medium: "warning",
  low: "success",
};
export const WORKFLOW_TONE: Record<string, BadgeVariant> = {
  applied: "warning",
  awarded: "success",
  active: "success",
  closed: "secondary",
  declined: "destructive",
  requested: "secondary",
  in_review: "info",
  changes_requested: "warning",
  approved: "success",
};

export const label = (list: readonly (readonly [string, string])[], v: string) =>
  list.find(([k]) => k === v)?.[1] ?? v;

/** Money for display; the server sends a decimal string and hides it from non-leads. */
export function money(amount: string | null, currency: string | null): string | null {
  if (amount === null) return null;
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: currency || "CAD",
    }).format(Number(amount));
  } catch {
    return `${amount} ${currency ?? ""}`.trim();
  }
}

/** Running totals per status from the dated entries (D136). */
export function totals(entries: { status: string; count: number }[]) {
  const t: Record<string, number> = { screened: 0, enrolled: 0, withdrawn: 0, completed: 0 };
  for (const e of entries) t[e.status] = (t[e.status] ?? 0) + e.count;
  return t;
}

export const PARTICIPANT_WARNING =
  "Don't enter names or identifying details here; keep participant records in REDCap or your approved system";
