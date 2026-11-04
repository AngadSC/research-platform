import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  DocumentFull,
  DocumentRow,
  DocumentSaveInput,
  Revision,
  RevisionRow,
} from "@/lib/api-types";

const base = (labId: string) => `/api/labs/${labId}`;
const listKey = (labId: string, projectId: string) =>
  ["labs", labId, "projects", projectId, "documents"] as const;
const docKey = (labId: string, id: string) => ["labs", labId, "documents", id] as const;

export function useDocuments(labId: string, projectId: string) {
  return useQuery({
    queryKey: listKey(labId, projectId),
    queryFn: () => api<DocumentRow[]>(`${base(labId)}/projects/${projectId}/documents/`),
  });
}

export function useCreateDocument(labId: string, projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (title: string) =>
      api<DocumentFull>(`${base(labId)}/projects/${projectId}/documents/`, {
        method: "POST",
        body: { title, content: [] },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: listKey(labId, projectId) }),
  });
}

export function useDocument(labId: string, id: string) {
  return useQuery({
    queryKey: docKey(labId, id),
    queryFn: () => api<DocumentFull>(`${base(labId)}/documents/${id}/`),
    // The editor owns its state once loaded; refetches only happen on an explicit reload.
    enabled: !!id,
    staleTime: Infinity,
    gcTime: 0,
  });
}

/** PUT with base_version. A stale save rejects with ApiError status 409 (body = DocumentConflict). */
export function useSaveDocument(labId: string, id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: DocumentSaveInput) =>
      api<DocumentFull>(`${base(labId)}/documents/${id}/`, { method: "PUT", body: v }),
    onSuccess: (doc) => {
      qc.setQueryData(docKey(labId, id), doc);
      void qc.invalidateQueries({ queryKey: ["labs", labId, "projects"] });
      void qc.invalidateQueries({ queryKey: [...docKey(labId, id), "revisions"] });
    },
  });
}

export function useRevisions(labId: string, id: string, enabled: boolean) {
  return useQuery({
    queryKey: [...docKey(labId, id), "revisions"],
    queryFn: () => api<RevisionRow[]>(`${base(labId)}/documents/${id}/revisions/`),
    enabled,
  });
}

export function useRevision(labId: string, id: string, version: number | null) {
  return useQuery({
    queryKey: [...docKey(labId, id), "revisions", version],
    queryFn: () => api<Revision>(`${base(labId)}/documents/${id}/revisions/${version}/`),
    enabled: version !== null,
  });
}

export function useRestoreRevision(labId: string, id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (version: number) =>
      api<DocumentFull>(`${base(labId)}/documents/${id}/revisions/${version}/restore/`, {
        method: "POST",
      }),
    onSuccess: (doc) => {
      qc.setQueryData(docKey(labId, id), doc);
      void qc.invalidateQueries({ queryKey: ["labs", labId, "projects"] });
      void qc.invalidateQueries({ queryKey: [...docKey(labId, id), "revisions"] });
    },
  });
}
