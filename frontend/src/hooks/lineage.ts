import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Lineage } from "@/lib/api-types";

export function useLineage(labId: string, projectId: string) {
  return useQuery({
    queryKey: ["labs", labId, "projects", projectId, "lineage"],
    queryFn: () => api<Lineage>(`/api/labs/${labId}/projects/${projectId}/lineage/`),
  });
}
