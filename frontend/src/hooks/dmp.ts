import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Dmp, DmpInput, DmpRevision } from "@/lib/api-types";

const base = (labId: string, projectId: string) =>
  `/api/labs/${labId}/projects/${projectId}/data-management-plan/`;

/** The project's data management plan (D180), its revisions, and save / approve / delete. */
export function useDmp(labId: string, projectId: string, withHistory: boolean) {
  const qc = useQueryClient();
  const key = ["labs", labId, "projects", projectId, "dmp"] as const;
  const refresh = () => qc.invalidateQueries({ queryKey: key });
  const plan = useQuery({ queryKey: key, queryFn: () => api<Dmp>(base(labId, projectId)) });
  const history = useQuery({
    queryKey: [...key, "revisions"],
    queryFn: () => api<DmpRevision[]>(`${base(labId, projectId)}revisions/`),
    enabled: withHistory,
  });
  const save = useMutation({
    mutationFn: (v: DmpInput) => api<Dmp>(base(labId, projectId), { method: "PATCH", body: v }),
    onSuccess: refresh,
  });
  const approve = useMutation({
    mutationFn: () => api<Dmp>(`${base(labId, projectId)}approve/`, { method: "POST" }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: () => api(base(labId, projectId), { method: "DELETE" }),
    onSuccess: refresh,
  });
  return { plan, history, save, approve, remove };
}
