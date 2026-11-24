import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-schema";

export type PageComment = components["schemas"]["PageComment"];

const key = (labId: string, path: string) => ["labs", labId, "page-comments", path];

/** The comments on one page of the app, oldest first. */
export function usePageComments(labId: string, path: string, enabled = true) {
  return useQuery({
    queryKey: key(labId, path),
    queryFn: () =>
      api<PageComment[]>(`/api/labs/${labId}/page-comments/?path=${encodeURIComponent(path)}`),
    enabled,
  });
}

export function useAddPageComment(labId: string, path: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { body: string; quote: string; page_label: string }) =>
      api<PageComment>(`/api/labs/${labId}/page-comments/`, {
        method: "POST",
        body: { path, ...body },
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: key(labId, path) }),
  });
}

export function useDeletePageComment(labId: string, path: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api<void>(`/api/labs/${labId}/page-comments/${id}/`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: key(labId, path) }),
  });
}
