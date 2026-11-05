import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import type {
  EthicsApproval,
  Funding,
  FundingInput,
  InstitutionResource,
  RecruitmentEntry,
  RecruitmentEntryInput,
  RecruitmentPlan,
  ReviewItem,
  ReviewItemInput,
} from "@/lib/api-types";

const lab = (labId: string) => `/api/labs/${labId}`;
const key = (labId: string, projectId: string) =>
  ["labs", labId, "projects", projectId, "workflow"] as const;

/** List + create/update/delete for one workflow collection (`P/<list>/`, `L/<flat>/<id>/`). */
function useCollection<T, I>(
  labId: string,
  projectId: string,
  name: "funding" | "review-items" | "recruitment-entries",
) {
  const qc = useQueryClient();
  const k = [...key(labId, projectId), name];
  const refresh = () => qc.invalidateQueries({ queryKey: key(labId, projectId) });
  const list = useQuery({
    queryKey: k,
    queryFn: () => api<T[]>(`${lab(labId)}/projects/${projectId}/${name}/`),
  });
  const create = useMutation({
    mutationFn: (v: I) =>
      api<T>(`${lab(labId)}/projects/${projectId}/${name}/`, { method: "POST", body: v }),
    onSuccess: refresh,
  });
  const update = useMutation({
    mutationFn: (v: { id: string; patch: Partial<I> }) =>
      api<T>(`${lab(labId)}/${name}/${v.id}/`, { method: "PATCH", body: v.patch }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`${lab(labId)}/${name}/${id}/`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  return { list, create, update, remove };
}

export const useFunding = (l: string, p: string) =>
  useCollection<Funding, FundingInput>(l, p, "funding");
export const useReviewItems = (l: string, p: string) =>
  useCollection<ReviewItem, ReviewItemInput>(l, p, "review-items");
export const useRecruitmentEntries = (l: string, p: string) =>
  useCollection<RecruitmentEntry, RecruitmentEntryInput>(l, p, "recruitment-entries");

export function useRecruitmentPlan(labId: string, projectId: string) {
  const qc = useQueryClient();
  const k = [...key(labId, projectId), "plan"];
  const url = `${lab(labId)}/projects/${projectId}/recruitment-plan/`;
  const plan = useQuery({ queryKey: k, queryFn: () => api<RecruitmentPlan>(url) });
  const save = useMutation({
    mutationFn: (v: Partial<RecruitmentPlan>) =>
      api<RecruitmentPlan>(url, { method: "PATCH", body: v }),
    onSuccess: (data) => qc.setQueryData(k, data),
  });
  return { plan, save };
}

/** The approvals linked to this project (D134). */
export function useProjectApprovals(labId: string, projectId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["labs", labId, "ethics", "project", projectId],
    queryFn: () => api<EthicsApproval[]>(`${lab(labId)}/ethics-approvals/?project=${projectId}`),
    enabled,
  });
}

/** The institution's links for a category. A missing or failing endpoint reads as no links,
 * never as a crash (D135). */
export function useInstitutionLinks(labId: string, category: "ethics" | "funding") {
  return useQuery({
    queryKey: ["labs", labId, "institution-resources", category],
    queryFn: async () => {
      try {
        return await api<InstitutionResource[]>(
          `${lab(labId)}/institution-resources/?category=${category}`,
        );
      } catch (e) {
        if (e instanceof ApiError) return [] as InstitutionResource[];
        throw e;
      }
    },
    retry: false,
    enabled: !!labId,
  });
}
