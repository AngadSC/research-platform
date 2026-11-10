import { useEffect } from "react";
import { useMatches } from "react-router";
import type { Crumb } from "@/components/shared/Breadcrumbs";
import { useApproval } from "@/hooks/ethics";
import { useDocument } from "@/hooks/documents";
import { usePaper } from "@/hooks/papers";
import { useProject } from "@/hooks/projects";
import { useRecord } from "@/hooks/research";
import { useLabs } from "@/hooks/workspace";
import type { RecentKind } from "@/lib/pins";
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
  const paperParam = matches.find((m) => m.params.paperId)?.params;
  const { data: paper } = usePaper(paperParam?.labId ?? "", paperParam?.paperId);
  const { kind, id } = matches.find((m) => m.params.id)?.params ?? {};
  const validKind = isKind(kind) ? kind : undefined;
  const { data: rec } = useRecord<AnyRecord>(
    projectParam?.labId ?? "",
    validKind ?? "datasets",
    validKind ? (id ?? "") : "",
  );
  const named: Record<string, { kind?: RecentKind; loaded: boolean }> = {
    "@lab": { loaded: !!labs },
    "@paper": { loaded: !!paper },
    "@project": { kind: "project", loaded: !!project },
    "@document": { kind: "document", loaded: !!doc },
    "@record": { kind: "record", loaded: !!rec },
    "@approval": { kind: "approval", loaded: !!approval },
  };
  return matches.flatMap((m) => {
    let crumb = (m.handle as { crumb?: string } | undefined)?.crumb;
    const item = crumb ? named[crumb] : undefined;
    if (crumb === "@lab") crumb = labs?.find((l) => l.id === m.params.labId)?.name ?? "Lab";
    if (crumb === "@project") crumb = project?.name ?? "Project";
    if (crumb === "@kind") crumb = isKind(m.params.kind) ? KINDS[m.params.kind].label : "Records";
    if (crumb === "@record") crumb = rec ? recordTitle(rec) : "Record";
    if (crumb === "@approval") crumb = approval?.approval_number ?? "Approval";
    if (crumb === "@document") crumb = doc?.title ?? "Document";
    if (crumb === "@paper") crumb = paper?.title ?? "Paper";
    return crumb
      ? [{ label: crumb, to: m.pathname, kind: item?.kind, pending: item && !item.loaded }]
      : [];
  });
}

/** The project id from the matched route, if the current page is inside a project. */
export function useCurrentProjectId(): string | undefined {
  return useMatches()
    .map((m) => m.params.projectId)
    .find(Boolean);
}

const LAST_LAB_KEY = "last-lab";

function readLastLab() {
  try {
    return localStorage.getItem(LAST_LAB_KEY);
  } catch {
    return null; // storage is blocked: pages outside a lab use the first lab
  }
}

/** The lab in the address. Pages outside a lab (Settings) keep the lab you were last in, so the
 * sidebar and its links stay; it is checked against your labs because storage can be stale. */
export function useCurrentLabId(): string | undefined {
  const inUrl = useMatches()
    .map((m) => m.params.labId)
    .find(Boolean);
  const { data: labs } = useLabs();
  useEffect(() => {
    if (!inUrl) return;
    try {
      localStorage.setItem(LAST_LAB_KEY, inUrl);
    } catch {
      // storage is blocked: nothing to remember
    }
  }, [inUrl]);
  if (inUrl) return inUrl;
  return (labs?.find((l) => l.id === readLastLab()) ?? labs?.[0])?.id;
}
