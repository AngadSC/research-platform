import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-schema";

export type Dashboard = components["schemas"]["Dashboard"];
export type DashProject = components["schemas"]["DashProject"];
export type DashPerson = components["schemas"]["DashPerson"];
export type TrainingExpiring = components["schemas"]["Expiring"];

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
