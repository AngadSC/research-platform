import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, upload } from "@/lib/api";
import type {
  Attachment,
  Paper,
  PaperCitations,
  PaperDetail,
  PaperDoiLookup,
  PaperInput,
  PaperNote,
} from "@/lib/api-types";

const base = (labId: string) => `/api/labs/${labId}/papers`;
const root = (labId: string) => ["labs", labId, "papers"] as const;
const body = (v: unknown) => ({ body: v });

export const paperPdfUrl = (labId: string, paperId: string) => `${base(labId)}/${paperId}/pdf/`;

export const usePapers = (labId: string, q: string) =>
  useQuery({
    queryKey: [...root(labId), "list", q],
    queryFn: () => api<Paper[]>(`${base(labId)}/?q=${encodeURIComponent(q)}`),
    placeholderData: keepPreviousData,
  });

export const usePaper = (labId: string, paperId: string | undefined) =>
  useQuery({
    queryKey: [...root(labId), "detail", paperId],
    queryFn: () => api<PaperDetail>(`${base(labId)}/${paperId}/`),
    enabled: !!labId && !!paperId,
  });

export const useCitations = (labId: string, paperId: string) =>
  useQuery({
    queryKey: [...root(labId), "citation", paperId],
    queryFn: () => api<PaperCitations>(`${base(labId)}/${paperId}/citation/`),
  });

export function lookupDoi(labId: string, doi: string) {
  return api<PaperDoiLookup>(`${base(labId)}/doi-lookup/?doi=${encodeURIComponent(doi)}`);
}

export function usePaperMutations(labId: string) {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: root(labId) });
  return {
    create: useMutation({
      mutationFn: (v: PaperInput) =>
        api<PaperDetail>(`${base(labId)}/`, { method: "POST", ...body(v) }),
      onSuccess: done,
    }),
    update: useMutation({
      mutationFn: ({ id, ...v }: PaperInput & { id: string }) =>
        api<PaperDetail>(`${base(labId)}/${id}/`, { method: "PATCH", ...body(v) }),
      onSuccess: done,
    }),
    remove: useMutation({
      mutationFn: (id: string) => api(`${base(labId)}/${id}/`, { method: "DELETE" }),
      onSuccess: done,
    }),
    addNote: useMutation({
      mutationFn: (v: { paperId: string; body: string }) =>
        api<PaperNote>(`${base(labId)}/${v.paperId}/notes/`, {
          method: "POST",
          ...body({ body: v.body }),
        }),
      onSuccess: done,
    }),
    editNote: useMutation({
      mutationFn: (v: { id: string; body: string }) =>
        api<PaperNote>(`/api/labs/${labId}/paper-notes/${v.id}/`, {
          method: "PATCH",
          ...body({ body: v.body }),
        }),
      onSuccess: done,
    }),
    removeNote: useMutation({
      mutationFn: (id: string) =>
        api(`/api/labs/${labId}/paper-notes/${id}/`, { method: "DELETE" }),
      onSuccess: done,
    }),
    uploadPdf: useMutation({
      mutationFn: (v: { id: string; file: File; onProgress?: (f: number) => void }) => {
        const form = new FormData();
        form.append("file", v.file);
        form.append("acknowledged_notice", "true");
        return upload<Attachment>(`${base(labId)}/${v.id}/pdf/`, form, v.onProgress);
      },
      onSuccess: done,
    }),
  };
}
