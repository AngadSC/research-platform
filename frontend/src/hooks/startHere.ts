import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { MyOnboardingItem, StartHerePin } from "@/lib/api-types";

const base = (labId: string) => `/api/labs/${labId}`;
const pinsKey = (labId: string) => ["labs", labId, "start-here"] as const;
const onboardingKey = (labId: string) => ["labs", labId, "my-onboarding"] as const;

/** Documents pinned for everyone (D351): lab documents first, then each project's. */
export function useStartHere(labId: string) {
  return useQuery({
    queryKey: pinsKey(labId),
    queryFn: () => api<StartHerePin[]>(`${base(labId)}/start-here/`),
  });
}

/** Pin, unpin or move one document in the Start here list. The server decides who may. */
export function usePinForEveryone(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: string; action: "pin" | "unpin" | "up" | "down" }) => {
      const url = `${base(labId)}/documents/${v.id}/pin/`;
      if (v.action === "pin") return api(url, { method: "POST" });
      if (v.action === "unpin") return api(url, { method: "DELETE" });
      return api(url, { method: "PATCH", body: { direction: v.action } });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: pinsKey(labId) }),
  });
}

/** The new-member checklist with this person's own ticks. */
export function useMyOnboarding(labId: string, enabled = true) {
  return useQuery({
    queryKey: onboardingKey(labId),
    queryFn: () => api<MyOnboardingItem[]>(`${base(labId)}/my-onboarding/`),
    enabled,
  });
}

export function useTickOnboarding(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: string; done: boolean }) =>
      api<MyOnboardingItem>(`${base(labId)}/my-onboarding/${v.id}/`, {
        method: "POST",
        body: { done: v.done },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: onboardingKey(labId) }),
  });
}
