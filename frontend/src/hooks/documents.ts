import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { api } from "@/lib/api";
import type {
  DocumentFull,
  DocumentRow,
  DocumentSaveInput,
  Folder,
  Revision,
  RevisionRow,
} from "@/lib/api-types";

const base = (labId: string) => `/api/labs/${labId}`;
const listKey = (labId: string, projectId: string) =>
  ["labs", labId, "projects", projectId, "documents"] as const;
const docKey = (labId: string, id: string) => ["labs", labId, "documents", id] as const;

/** `pollMs` re-fetches on that interval while the tab is visible (the stale-document banner). */
export function useDocuments(labId: string, projectId: string, pollMs?: number) {
  return useQuery({
    queryKey: listKey(labId, projectId),
    queryFn: () => api<DocumentRow[]>(`${base(labId)}/projects/${projectId}/documents/`),
    refetchInterval: pollMs,
  });
}

export interface DocumentCreate {
  title: string;
  folder?: string | null;
  /** A pasted Google or Microsoft link: the server normalises it into a frame URL. */
  embed_url?: string;
}

export function useCreateDocument(labId: string, projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: string | DocumentCreate) =>
      api<DocumentFull>(`${base(labId)}/projects/${projectId}/documents/`, {
        method: "POST",
        body: { content: [], ...(typeof input === "string" ? { title: input } : input) },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: listKey(labId, projectId) }),
  });
}

/** Soft delete (D24). `edit_content`. */
export function useDeleteDocument(labId: string, projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api(`${base(labId)}/documents/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: listKey(labId, projectId) }),
  });
}

/** The folder being browsed is in the URL (`?folder=`), so the back button and links work. */
export function useCurrentFolder(): string | null {
  const [params] = useSearchParams();
  return params.get("folder");
}

/** The project's folder tree, shared by the Documents and Files tabs. */
export function useFolders(labId: string, projectId: string) {
  return useQuery({
    queryKey: [...listKey(labId, projectId).slice(0, 4), "folders"],
    queryFn: () => api<Folder[]>(`${base(labId)}/projects/${projectId}/folders/`),
  });
}

export function useFolderActions(labId: string, projectId: string) {
  const qc = useQueryClient();
  const onSuccess = () => qc.invalidateQueries({ queryKey: listKey(labId, projectId).slice(0, 4) });
  return {
    create: useMutation({
      mutationFn: (v: { name: string; parent: string | null }) =>
        api<Folder>(`${base(labId)}/projects/${projectId}/folders/`, { method: "POST", body: v }),
      onSuccess,
    }),
    rename: useMutation({
      mutationFn: (v: { id: string; name: string }) =>
        api<Folder>(`${base(labId)}/folders/${v.id}/`, {
          method: "PATCH",
          body: { name: v.name },
        }),
      onSuccess,
    }),
    remove: useMutation({
      mutationFn: (id: string) => api(`${base(labId)}/folders/${id}/`, { method: "DELETE" }),
      onSuccess,
    }),
    move: useMutation({
      mutationFn: (v: { kind: "documents" | "attachments"; id: string; folder: string | null }) =>
        api(`${base(labId)}/${v.kind}/${v.id}/move/`, {
          method: "POST",
          body: { folder: v.folder },
        }),
      onSuccess,
    }),
  };
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
