import { useMatches } from "react-router";
import type { Crumb } from "@/components/shared/Breadcrumbs";
import { useDocument } from "@/hooks/documents";
import { useProject } from "@/hooks/projects";
import { useLabs } from "@/hooks/workspace";

/** Routes declare `handle: { crumb: "Label" }`. "@lab" and "@project" become the current lab and project names. */
export function useCrumbs(): Crumb[] {
  const matches = useMatches();
  const { data: labs } = useLabs();
  const projectParam = matches.find((m) => m.params.projectId)?.params;
  const { data: project } = useProject(projectParam?.labId, projectParam?.projectId);
  const docId = matches.find((m) => m.params.documentId)?.params.documentId ?? "";
  const { data: doc } = useDocument(projectParam?.labId ?? "", docId);
  return matches.flatMap((m) => {
    let crumb = (m.handle as { crumb?: string } | undefined)?.crumb;
    if (crumb === "@lab") crumb = labs?.find((l) => l.id === m.params.labId)?.name ?? "Lab";
    if (crumb === "@project") crumb = project?.name ?? "Project";
    if (crumb === "@document") crumb = doc?.title ?? "Document";
    return crumb ? [{ label: crumb, to: m.pathname }] : [];
  });
}

/** The lab id from the matched route, if the current page is inside a lab. */
export function useCurrentLabId(): string | undefined {
  return useMatches()
    .map((m) => m.params.labId)
    .find(Boolean);
}
