import { useQuery } from "@tanstack/react-query";
import type { Person } from "@/components/composer/RichComposer";
import { api } from "@/lib/api";
import { personName, type Membership, type ProjectMembership } from "@/lib/api-types";

/** Who can be @mentioned (D260): a project's members, or with no `projectId` the whole lab. These
 * are the same lists, with the same query keys, as the member pages, so they are usually cached. */
export function useMentionPeople(labId: string, projectId?: string): Person[] | undefined {
  const lab = useQuery({
    queryKey: ["labs", labId, "members"],
    queryFn: () => api<Membership[]>(`/api/labs/${labId}/members/`),
    enabled: !projectId,
  });
  const project = useQuery({
    queryKey: ["labs", labId, "projects", projectId, "members"],
    queryFn: () => api<ProjectMembership[]>(`/api/labs/${labId}/projects/${projectId}/members/`),
    enabled: !!projectId,
  });
  const rows = projectId ? project.data : lab.data;
  return rows?.map((m) => ({ id: m.user.id, name: personName(m.user) }));
}
