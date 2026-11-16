import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { NotebookEntry, NotebookEntryInput } from "@/lib/api-types";

const body = (v: unknown) => ({ body: v as Record<string, unknown> });

export type ExportFormat = "md" | "html" | "json";

/** Your own notebook (no `projectId`) or a project's shared one (D330). */
export function useNotebook(labId: string, projectId?: string) {
  const qc = useQueryClient();
  const root = projectId
    ? `/api/labs/${labId}/projects/${projectId}/notebook/`
    : `/api/labs/${labId}/notebook/`;
  const key = ["labs", labId, "notebook", projectId ?? "mine"];
  const list = useQuery({ queryKey: key, queryFn: () => api<NotebookEntry[]>(root) });
  const done = () => qc.invalidateQueries({ queryKey: key });
  const create = useMutation({
    mutationFn: (v: NotebookEntryInput) => api<NotebookEntry>(root, { method: "POST", ...body(v) }),
    onSuccess: done,
  });
  const update = useMutation({
    mutationFn: (v: { id: string; patch: Partial<NotebookEntryInput> }) =>
      api<NotebookEntry>(`${root}${v.id}/`, { method: "PATCH", ...body(v.patch) }),
    onSuccess: done,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`${root}${id}/`, { method: "DELETE" }),
    onSuccess: done,
  });
  const lock = useMutation({
    mutationFn: (id: string) => api<NotebookEntry>(`${root}${id}/lock/`, { method: "POST" }),
    onSuccess: done,
  });
  const exportUrl = (fmt: ExportFormat, from = "", to = "") => {
    const q = new URLSearchParams({ fmt });
    if (from) q.set("from", from);
    if (to) q.set("to", to);
    return `${root}export/?${q}`;
  };
  return { list, create, update, remove, lock, exportUrl };
}
