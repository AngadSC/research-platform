import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Handover } from "@/lib/api-types";

/** Each visit generates (and audits) a fresh report, so it is never cached or refetched on focus. */
export function useHandover(path: string) {
  return useQuery({
    queryKey: ["handover", path],
    queryFn: () => api<Handover>(path),
    gcTime: 0,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

const lab = (labId: string) => `/api/labs/${labId}`;
const send = (method: string, path: string, body: unknown) => api(path, { method, body });

/** Hand one task to a new assignee. The server refuses people who are not on the project. */
export const reassignTask = (labId: string, taskId: string, userId: string) =>
  send("PATCH", `${lab(labId)}/tasks/${taskId}/`, { assignee: userId });

export const reassignDataset = (labId: string, datasetId: string, userId: string) =>
  send("PATCH", `${lab(labId)}/datasets/${datasetId}/`, { controlled_by: userId });

/** Make someone a project lead: change their role if they are already a member, else add them. */
export async function addProjectLead(labId: string, projectId: string, userId: string) {
  const path = `${lab(labId)}/projects/${projectId}/members/`;
  const current = await api<{ id: string; user: { id: string } }[]>(path);
  const existing = current.find((m) => m.user.id === userId);
  return existing
    ? send("PATCH", `${lab(labId)}/project-members/${existing.id}/`, { role: "lead" })
    : send("POST", path, { user: userId, role: "lead" });
}
