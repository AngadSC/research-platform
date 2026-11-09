import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { SearchHit } from "@/lib/api-types";

const TYPE_LABELS: Record<string, string> = {
  project: "Projects",
  task: "Tasks",
  document: "Documents",
  dataset: "Datasets",
  analysis: "Analyses",
  result: "Results",
  decision: "Decisions",
  manuscript: "Manuscripts",
  ethics: "Ethics approvals",
  link: "Linked files",
  paper: "Papers",
  paper_note: "Paper notes",
};

/** Hits grouped by type, in the order the server sent them. */
export function groupHits(hits: SearchHit[]): [string, SearchHit[]][] {
  const groups = new Map<string, SearchHit[]>();
  for (const h of hits) groups.set(h.type, [...(groups.get(h.type) ?? []), h]);
  return [...groups].map(([type, items]) => [TYPE_LABELS[type] ?? type, items]);
}

export const SEARCH_DELAY_MS = 250;
export const MIN_QUERY = 2;

/** Lab-wide search (D93). Waits for a pause in typing; a newer query aborts the older request. */
export function useLabSearch(labId: string | undefined, text: string, delay = SEARCH_DELAY_MS) {
  const [q, setQ] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setQ(text.trim()), delay);
    return () => clearTimeout(t);
  }, [text, delay]);
  const enabled = !!labId && q.length >= MIN_QUERY;
  const query = useQuery({
    queryKey: ["labs", labId, "search", q],
    queryFn: ({ signal }) =>
      api<{ results: SearchHit[] }>(`/api/labs/${labId}/search/?q=${encodeURIComponent(q)}`, {
        signal,
      }).then((r) => r.results),
    enabled,
    staleTime: 30_000,
  });
  return {
    hits: enabled ? (query.data ?? []) : [],
    loading: text.trim().length >= MIN_QUERY && (q !== text.trim() || query.isFetching),
    error: enabled && query.isError,
  };
}
