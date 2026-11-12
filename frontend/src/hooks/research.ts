import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { markMine } from "@/hooks/liveRefresh";
import type { Kind } from "@/lib/research";

export const root = (labId: string) => ["labs", labId, "research"] as const;
const lab = (labId: string) => `/api/labs/${labId}`;

export function useRecords<T>(labId: string, projectId: string, kind: Kind, pollMs?: number) {
  return useQuery({
    queryKey: [...root(labId), "list", projectId, kind],
    queryFn: () => api<T[]>(`${lab(labId)}/projects/${projectId}/${kind}/`),
    refetchInterval: pollMs,
  });
}
export function useRecord<T>(labId: string, kind: Kind, id: string) {
  return useQuery({
    queryKey: [...root(labId), "one", kind, id],
    queryFn: () => api<T>(`${lab(labId)}/${kind}/${id}/`),
    enabled: !!id,
  });
}
/** Create when `id` is absent, otherwise PATCH. */
export function useSaveRecord<T>(labId: string, projectId: string, kind: Kind, id?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: Record<string, unknown>) =>
      id
        ? api<T>(`${lab(labId)}/${kind}/${id}/`, { method: "PATCH", body: v })
        : api<T>(`${lab(labId)}/projects/${projectId}/${kind}/`, { method: "POST", body: v }),
    onSuccess: (r) => {
      markMine((r as { id?: string } | undefined)?.id);
      return qc.invalidateQueries({ queryKey: root(labId) });
    },
  });
}
export function useDeleteRecord(labId: string, kind: Kind) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api(`${lab(labId)}/${kind}/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: root(labId) }),
  });
}

export interface ExportData {
  exported_at: string;
  [k: string]: unknown;
}
export const useExportProject = (labId: string, projectId: string) =>
  useMutation({
    mutationFn: () =>
      api<ExportData>(`${lab(labId)}/projects/${projectId}/export/`, { method: "POST" }),
  });

/** Download JSON as a file via a temporary link. */
export function saveJson(data: unknown, filename: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
