import { useMatches } from "react-router";
import type { Crumb } from "@/components/shared/Breadcrumbs";
import { useApproval } from "@/hooks/ethics";
import { useDocument } from "@/hooks/documents";
import { useProject } from "@/hooks/projects";
import { useRecord } from "@/hooks/research";
import { useLabs } from "@/hooks/workspace";
import { isKind, KINDS, recordTitle, type AnyRecord } from "@/lib/research";

/** Routes declare `handle: { crumb: "Label" }`. "@lab" and "@project" become the current lab and project names. */
export function useCrumbs(): Crumb[] {
  const matches = useMatches();
  const { data: labs } = useLabs();
  const projectParam = matches.find((m) => m.params.projectId)?.params;
  const { data: project } = useProject(projectParam?.labId, projectParam?.projectId);
  const docId = matches.find((m) => m.params.documentId)?.params.documentId ?? "";
  const { data: doc } = useDocument(projectParam?.labId ?? "", docId);
  const approvalId = matches.find((m) => m.params.approvalId)?.params.approvalId;
  const { data: approval } = useApproval(
    matches.find((m) => m.params.labId)?.params.labId,
    approvalId,
  );
  const { kind, id } = matches.find((m) => m.params.id)?.params ?? {};
  const validKind = isKind(kind) ? kind : undefined;
  const { data: rec } = useRecord<AnyRecord>(
    projectParam?.labId ?? "",
    validKind ?? "datasets",
    validKind ? (id ?? "") : "",
  );
  return matches.flatMap((m) => {
    let crumb = (m.handle as { crumb?: string } | undefined)?.crumb;
    if (crumb === "@lab") crumb = labs?.find((l) => l.id === m.params.labId)?.name ?? "Lab";
    if (crumb === "@project") crumb = project?.name ?? "Project";
    if (crumb === "@kind") crumb = isKind(m.params.kind) ? KINDS[m.params.kind].label : "Records";
    if (crumb === "@record") crumb = rec ? recordTitle(rec) : "Record";
    if (crumb === "@approval") crumb = approval?.approval_number ?? "Approval";
    if (crumb === "@document") crumb = doc?.title ?? "Document";
    return crumb ? [{ label: crumb, to: m.pathname }] : [];
  });
}

/** The project id from the matched route, if the current page is inside a project. */
export function useCurrentProjectId(): string | undefined {
  return useMatches()
    .map((m) => m.params.projectId)
    .find(Boolean);
}

/** The lab id from the matched route, if the current page is inside a lab. */
export function useCurrentLabId(): string | undefined {
  return useMatches()
    .map((m) => m.params.labId)
    .find(Boolean);
}
