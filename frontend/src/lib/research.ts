import type { Analysis, Dataset, Decision, Manuscript, ResearchResult } from "@/lib/api-types";

export type Kind = "datasets" | "analyses" | "results" | "decisions" | "manuscripts";
export type AnyRecord = Dataset | Analysis | ResearchResult | Decision | Manuscript;

/** Labels and plain-words explanations; the empty-state copy is binding vocabulary (UI.md). */
export const KINDS: Record<Kind, { label: string; one: string; blurb: string }> = {
  datasets: {
    label: "Datasets",
    one: "dataset",
    blurb: "A dataset record points to where data lives. We never store the data itself.",
  },
  analyses: {
    label: "Analyses",
    one: "analysis",
    blurb:
      "An analysis record says which code, run on which dataset versions, produced your results.",
  },
  results: {
    label: "Results",
    one: "result",
    blurb: "A result is a finding, with its figures, that came out of one analysis.",
  },
  decisions: {
    label: "Decisions",
    one: "decision",
    blurb: "A decision is a short note of a choice the lab made, and why, with supporting records.",
  },
  manuscripts: {
    label: "Manuscripts",
    one: "manuscript",
    blurb:
      "A manuscript record links to your paper (Overleaf or Google Docs) and the results it uses.",
  },
};
export const KIND_LIST = Object.keys(KINDS) as Kind[];
export const isKind = (k: string | undefined): k is Kind => !!k && k in KINDS;

export const isHttpUrl = (s: string) => {
  try {
    const p = new URL(s).protocol;
    return p === "http:" || p === "https:";
  } catch {
    return false;
  }
};
export const isCommit = (s: string) => /^[0-9a-f]{7,40}$/i.test(s);

export const MANUSCRIPT_STATUSES = [
  ["drafting", "Drafting"],
  ["submitted", "Submitted"],
  ["in_review", "In review"],
  ["accepted", "Accepted"],
  ["published", "Published"],
] as const;

export const recordTitle = (r: AnyRecord) => ("name" in r ? r.name : r.title);
