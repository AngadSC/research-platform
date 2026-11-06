import { useMemo } from "react";
import { useNavigate } from "react-router";
import { useDocuments } from "@/hooks/documents";
import { useProjects } from "@/hooks/projects";
import { useRecords } from "@/hooks/research";
import { useRegisterCommands, type Command } from "@/lib/commands";
import { recordPath, SECTIONS } from "@/lib/workflow";
import { KIND_LIST, KINDS, recordTitle, type AnyRecord, type Kind } from "@/lib/research";

/** D45, D132: the lab's projects, the current project's documents and research records, plus quick creates. */
export function useProjectCommands(labId: string, projectId: string, canEdit: boolean) {
  const navigate = useNavigate();
  const projects = useProjects(labId).data;
  const docs = useDocuments(labId, projectId).data;
  // Fixed order, so hook order is stable.
  const recs = KIND_LIST.map((k) => useRecords<AnyRecord>(labId, projectId, k).data); // eslint-disable-line react-hooks/rules-of-hooks
  const sig = recs.map((r) => r?.map((x) => x.id + recordTitle(x)).join("|")).join();

  useRegisterCommands(
    useMemo(() => {
      const p = `/labs/${labId}/projects/${projectId}`;
      const go = (to: string) => () => void navigate(to);
      const out: Command[] = [
        {
          id: "chat:open",
          label: "Open project chat",
          group: "Actions",
          onSelect: go(`${p}/chat`),
        },
        ...(projects ?? []).map((x) => ({
          id: `project:${x.id}`,
          label: `Go to project: ${x.name}`,
          group: "Projects",
          onSelect: go(`/labs/${labId}/projects/${x.id}/overview`),
        })),
        ...SECTIONS.map(([tab, name]) => ({
          id: `workflow:${tab}`,
          label: `Go to Workflow: ${name}`,
          group: "Workflow",
          onSelect: go(`${p}/workflow/${tab}`),
        })),
        ...(docs ?? []).map((d) => ({
          id: `doc:${d.id}`,
          label: `Document: ${d.title}`,
          group: "Documents",
          onSelect: go(`${p}/documents/${d.id}`),
        })),
        ...KIND_LIST.flatMap((k: Kind, i) =>
          (recs[i] ?? []).map((r) => ({
            id: `research:${k}:${r.id}`,
            label: `${KINDS[k].one[0]!.toUpperCase()}${KINDS[k].one.slice(1)}: ${recordTitle(r)}`,
            group: "Research",
            onSelect: go(recordPath(p, k, r.id)),
          })),
        ),
      ];
      if (canEdit)
        for (const k of ["datasets", "analyses"] as const)
          out.push({
            id: `research:new:${k}`,
            label: `New ${KINDS[k].one}`,
            group: "Actions",
            onSelect: go(recordPath(p, k, "new")),
          });
      return out;
      // eslint-disable-next-line react-hooks/exhaustive-deps -- `sig` stands in for recs
    }, [labId, projectId, canEdit, navigate, projects, docs, sig]),
  );
}
