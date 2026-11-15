import type { RegistryColumn } from "@/lib/api-types";

type Category = RegistryColumn["category"];

export interface TemplateColumn {
  name: string;
  category: Category;
  required?: boolean;
}

export interface ExperimentTemplate {
  id: string;
  name: string;
  blurb: string;
  columns: TemplateColumn[];
}

/** Starting points by kind of study. Pure suggestions: every column can be changed or removed. */
export const TEMPLATES: ExperimentTemplate[] = [
  {
    id: "interview",
    name: "Interview study",
    blurb: "Consent, a recorded session, then transcript and translation.",
    columns: [
      { name: "Consent form", category: "consent" },
      { name: "Recording", category: "session" },
      { name: "Transcript", category: "transcript" },
      { name: "Translation", category: "translation", required: false },
    ],
  },
  {
    id: "survey",
    name: "Survey or questionnaire",
    blurb: "Consent, the questionnaire, and scoring.",
    columns: [
      { name: "Consent form", category: "consent" },
      { name: "Questionnaire", category: "questionnaire" },
      { name: "Scoring", category: "scoring" },
    ],
  },
  {
    id: "lab-task",
    name: "Lab task or experiment",
    blurb: "Consent, a questionnaire before, the session, then scoring.",
    columns: [
      { name: "Consent form", category: "consent" },
      { name: "Pre-session questionnaire", category: "questionnaire" },
      { name: "Session data", category: "session" },
      { name: "Scoring", category: "scoring" },
    ],
  },
  {
    id: "longitudinal",
    name: "Longitudinal (repeated visits)",
    blurb: "Consent once, then the same data at each visit.",
    columns: [
      { name: "Consent form", category: "consent" },
      { name: "Baseline session", category: "session" },
      { name: "Follow-up 1", category: "session" },
      { name: "Follow-up 2", category: "session", required: false },
      { name: "Scoring", category: "scoring" },
    ],
  },
  {
    id: "observation",
    name: "Observation",
    blurb: "Consent, field notes and a coded record.",
    columns: [
      { name: "Consent form", category: "consent" },
      { name: "Field notes", category: "session" },
      { name: "Coding", category: "scoring" },
    ],
  },
];

/** Columns of a template that are not already present (matched by name, ignoring case). */
export function missingColumns(t: ExperimentTemplate, existing: { name: string }[]) {
  const have = new Set(existing.map((c) => c.name.trim().toLowerCase()));
  return t.columns.filter((c) => !have.has(c.name.toLowerCase()));
}
