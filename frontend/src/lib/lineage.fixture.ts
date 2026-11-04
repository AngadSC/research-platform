import type { Lineage, LineageKind, LineageNode } from "@/lib/api-types";

const n = (
  kind: LineageKind,
  key: string,
  label: string,
  subtitle: string,
  meta: Record<string, unknown> = {},
): LineageNode => ({ id: `${kind}:${key}`, kind, label, subtitle, href_id: key, meta });
const e = (source: string, target: string, kind: LineageKind) => ({
  id: `${source}>${target}`,
  source,
  target,
  kind,
});

export const COMMIT = "9fceb02d0c1c8a7d4f3b2a1e6d5c4b3a29181716";

/** Two dataset versions feed one analysis that makes two results; one result is in a manuscript. */
export const sample: Lineage = {
  nodes: [
    n("manuscript", "m1", "Gut paper", "draft", {
      status: "draft",
      url: "https://example.org/paper",
    }),
    n("result", "r2", "Figure 2", "Microbiome run", { summary: "Second figure" }),
    n("result", "r1", "Figure 1", "Microbiome run", { summary: "Diversity drops" }),
    n("analysis", "a1", "Microbiome run", COMMIT.slice(0, 7), {
      code_repo_url: "https://github.com/lab/gut",
      code_commit: COMMIT,
      ran_by: "Ada",
    }),
    n("dataset", "d2", "Gut samples", "v2", { version_label: "v2", checksum: "sha256-bbb" }),
    n("dataset", "d1", "Gut samples", "v1", { version_label: "v1", checksum: "sha256-aaa" }),
    n("decision", "x1", "Drop outliers", "2026-02-01", {
      decided_on: "2026-02-01",
      rationale: "Noise",
    }),
  ],
  edges: [
    e("dataset:d1", "dataset:d2", "dataset"),
    e("dataset:d2", "analysis:a1", "dataset"),
    e("analysis:a1", "result:r1", "analysis"),
    e("analysis:a1", "result:r2", "analysis"),
    e("result:r1", "manuscript:m1", "result"),
    e("decision:x1", "analysis:a1", "decision"),
  ],
};
