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

/** What an entry says about inventory and protocols (D332). Only the author's own text, read for
 * them: each suggestion is accepted with a click, and nothing is taken from stock before that. */
export interface UseHint {
  request_id: string;
  item: string;
  item_name: string;
  item_unit: string;
  stock: string;
  amount: string;
  unit: string;
  snippet: string;
  status: "new" | "logged" | "reversed" | "possible_duplicate" | "not_enough";
}
export interface ProtocolChange {
  protocol: string;
  item_name: string;
  protocol_amount: string;
  noted_amount: string;
}
export interface EntryHints {
  uses: UseHint[];
  protocol_changes: ProtocolChange[];
}

export function useEntryHints(
  labId: string,
  projectId: string | undefined,
  entryId: string,
  enabled: boolean,
) {
  const qc = useQueryClient();
  const root = projectId
    ? `/api/labs/${labId}/projects/${projectId}/notebook/`
    : `/api/labs/${labId}/notebook/`;
  const key = ["labs", labId, "notebook", projectId ?? "mine", entryId, "hints"];
  const hints = useQuery({
    queryKey: key,
    queryFn: () => api<EntryHints>(`${root}${entryId}/hints/`),
    enabled,
  });
  const take = useMutation({
    mutationFn: (v: { hint: UseHint; title: string }) =>
      api(`/api/labs/${labId}/inventory/${v.hint.item}/usage/`, {
        method: "POST",
        ...body({
          amount: v.hint.amount,
          unit: v.hint.unit,
          project: projectId ?? null,
          note: `From notebook: ${v.title}`.slice(0, 300),
          request_id: v.hint.request_id,
        }),
      }),
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: key }),
        qc.invalidateQueries({ queryKey: ["labs", labId, "inventory"] }),
      ]),
  });
  return { hints, take };
}
