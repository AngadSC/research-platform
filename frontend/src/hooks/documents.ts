import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { markMine } from "@/hooks/liveRefresh";
import type { Person } from "@/components/composer/RichComposer";
import { api } from "@/lib/api";
import {
  personName,
  type DocumentComment,
  type DocumentFull,
  type DocumentRow,
  type DocumentSaveInput,
  type Folder,
  type Revision,
  type RevisionRow,
  type User,
} from "@/lib/api-types";

type Me = User & { preferences?: { recents?: { url: string }[] } };
const base = (labId: string) => `/api/labs/${labId}`;
const listKey = (labId: string, projectId: string) =>
  ["labs", labId, "projects", projectId, "documents"] as const;
const docKey = (labId: string, id: string) => ["labs", labId, "documents", id] as const;
/** `projectId` "" is the lab-wide collection (D233). After creation both kinds share a route. */
const collection = (labId: string, projectId: string) =>
  projectId ? `${base(labId)}/projects/${projectId}/documents/` : `${base(labId)}/lab-documents/`;

/** `pollMs` re-fetches on that interval while the tab is visible (the stale-document banner). */
export function useDocuments(labId: string, projectId: string, pollMs?: number, enabled = true) {
  return useQuery({
    queryKey: listKey(labId, projectId),
    queryFn: () => api<DocumentRow[]>(collection(labId, projectId)),
    refetchInterval: pollMs,
    enabled,
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
      api<DocumentFull>(collection(labId, projectId), {
        method: "POST",
        body: { content: [], ...(typeof input === "string" ? { title: input } : input) },
      }),
    onSuccess: (d) => {
      markMine(d?.id);
      return qc.invalidateQueries({ queryKey: listKey(labId, projectId) });
    },
  });
}

/** Soft delete (D24). `edit_content`. */
export function useDeleteDocument(labId: string, projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api(`${base(labId)}/documents/${id}/`, { method: "DELETE" }),
    onSuccess: (_, id) => {
      // Drop it from Recents now, so the cached list can never be saved back with it in.
      qc.setQueryData<Me>(["me"], (m) => {
        const recents = m?.preferences?.recents;
        return m && recents
          ? {
              ...m,
              preferences: {
                ...m.preferences,
                recents: recents.filter((r) => !r.url.includes(id)),
              },
            }
          : m;
      });
      void qc.invalidateQueries({ queryKey: ["me"] });
      return qc.invalidateQueries({ queryKey: listKey(labId, projectId) });
    },
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
    /** Rename, and/or tick or clear "Identifies participants" (ticking flags the contents). */
    update: useMutation({
      mutationFn: ({
        id,
        ...body
      }: {
        id: string;
        name?: string;
        contains_participant_data?: boolean;
      }) => api<Folder>(`${base(labId)}/folders/${id}/`, { method: "PATCH", body }),
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

/** VISION A3: tick or clear "Identifies participants" on a document or file. */
export function useParticipantFlag(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { kind: "documents" | "attachments"; id: string; value: boolean }) =>
      api(`${base(labId)}/${v.kind}/${v.id}/`, {
        method: "PATCH",
        body: { contains_participant_data: v.value },
      }),
    // the project lists only: an open document keeps its editor state (DocumentPage tracks it)
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labs", labId, "projects"] }),
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
    mutationFn: ({ keepalive, ...v }: DocumentSaveInput & { keepalive?: boolean }) =>
      api<DocumentFull>(`${base(labId)}/documents/${id}/`, { method: "PUT", body: v, keepalive }),
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

/** Who can be @mentioned in a document's comments: everyone who can read it, but you. */
export function useCommentPeople(labId: string, documentId: string): Person[] | undefined {
  const { data } = useQuery({
    queryKey: [...docKey(labId, documentId), "comment-people"],
    queryFn: () =>
      api<{ id: string; email: string; display_name?: string }[]>(
        `${base(labId)}/documents/${documentId}/comment-people/`,
      ),
  });
  return data?.map((u) => ({ id: u.id, name: personName(u) }));
}

/** Comments on a document (lab-wide ones too). Re-fetched every 15 seconds while visible. */
export function useDocumentComments(labId: string, documentId: string) {
  const qc = useQueryClient();
  const url = `${base(labId)}/documents/${documentId}/comments/`;
  const key = [...docKey(labId, documentId), "comments"];
  const list = useQuery({
    queryKey: key,
    queryFn: () => api<DocumentComment[]>(url),
    refetchInterval: 15_000,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: key });
  const create = useMutation({
    mutationFn: (v: { body: string; quote?: string; parent?: string }) =>
      api<DocumentComment>(url, { method: "POST", body: v }),
    onSuccess: refresh,
  });
  const resolve = useMutation({
    mutationFn: (v: { id: string; resolved: boolean }) =>
      api<DocumentComment>(`${url}${v.id}/`, { method: "PATCH", body: { resolved: v.resolved } }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`${url}${id}/`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  return { list, create, resolve, remove };
}
