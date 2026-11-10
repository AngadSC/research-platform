import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-schema";

export type Dashboard = components["schemas"]["Dashboard"];
export type DashProject = components["schemas"]["DashProject"];
export type DashPerson = components["schemas"]["DashPerson"];
export type TrainingExpiring = components["schemas"]["Expiring"];
export type Contributions = components["schemas"]["Contributions"];
export type GettingStarted = components["schemas"]["GettingStarted"];

const gettingStartedKey = (labId: string) => ["labs", labId, "getting-started"];

/** The checklist on Home (D234). An error means "no checklist", not a broken page. */
export function useGettingStarted(labId: string) {
  return useQuery({
    queryKey: gettingStartedKey(labId),
    queryFn: () => api<GettingStarted>(`/api/labs/${labId}/getting-started/`),
  });
}

export function useSetGettingStartedDismissed(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (dismissed: boolean) =>
      api<GettingStarted>(`/api/labs/${labId}/getting-started/`, {
        method: "POST",
        body: { dismissed },
      }),
    onSuccess: (data) => qc.setQueryData(gettingStartedKey(labId), data),
  });
}

/** The PI dashboard (D170). Only ask when the account has `manage_lab`. */
export function useDashboard(labId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["labs", labId, "dashboard"],
    queryFn: () => api<Dashboard>(`/api/labs/${labId}/dashboard/`),
    enabled: !!labId && enabled,
  });
}

/** The "Training expiring" card (D174). An error means "no card", not a broken page. */
export function useTrainingExpiring(labId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["labs", labId, "training", "expiring"],
    queryFn: () => api<TrainingExpiring>(`/api/labs/${labId}/training/expiring/`),
    enabled: !!labId && enabled,
  });
}

/** The dashboard's contribution graph: the whole lab, or one member when `userId` is given. */
export function useContributions(labId: string | undefined, userId?: string) {
  return useQuery({
    queryKey: ["labs", labId, "contributions", userId ?? "everyone"],
    queryFn: () =>
      api<Contributions>(
        `/api/labs/${labId}/contributions/${userId ? `?user=${encodeURIComponent(userId)}` : ""}`,
      ),
    enabled: !!labId,
    placeholderData: (previous) => previous,
  });
}
