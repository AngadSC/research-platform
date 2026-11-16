import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Subject, SubjectInput } from "@/lib/api-types";

const base = (labId: string) => `/api/labs/${labId}`;
const body = (v: unknown) => ({ body: v as Record<string, unknown> });

/** A project's non-human subjects: animals, strains, cell lines, samples (D329). */
export function useSubjects(labId: string, projectId: string) {
  const qc = useQueryClient();
  const key = ["labs", labId, "projects", projectId, "subjects"];
  const list = useQuery({
    queryKey: key,
    queryFn: () => api<Subject[]>(`${base(labId)}/projects/${projectId}/subjects/`),
  });
  const done = () => qc.invalidateQueries({ queryKey: key });
  const create = useMutation({
    mutationFn: (v: SubjectInput) =>
      api<Subject>(`${base(labId)}/projects/${projectId}/subjects/`, {
        method: "POST",
        ...body(v),
      }),
    onSuccess: done,
  });
  const update = useMutation({
    mutationFn: (v: { id: string; patch: Partial<SubjectInput> }) =>
      api<Subject>(`${base(labId)}/subjects/${v.id}/`, { method: "PATCH", ...body(v.patch) }),
    onSuccess: done,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`${base(labId)}/subjects/${id}/`, { method: "DELETE" }),
    onSuccess: done,
  });
  return { list, create, update, remove };
}

export const subjectsExportUrl = (labId: string, projectId: string) =>
  `${base(labId)}/projects/${projectId}/subjects/export/`;
