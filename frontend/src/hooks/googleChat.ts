import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { GoogleChatSpace, GoogleChatStatus } from "@/lib/api-types";

const base = (labId: string) => `/api/labs/${labId}/chat/google/`;
const key = (labId: string) => ["labs", labId, "google-chat"];

/** D318: whether the lab chat is linked to a Google Chat space, and what you may do about it. */
export function useGoogleChat(labId: string) {
  const qc = useQueryClient();
  const status = useQuery({
    queryKey: key(labId),
    queryFn: () => api<GoogleChatStatus>(base(labId)),
    enabled: !!labId,
  });
  const link = useMutation({
    mutationFn: (space: string) =>
      api<GoogleChatStatus>(base(labId), { method: "PUT", body: { space } }),
    onSuccess: (data) => qc.setQueryData(key(labId), data),
  });
  const unlink = useMutation({
    mutationFn: () => api(base(labId), { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(labId) }),
  });
  return { status, link, unlink };
}

/** The spaces your own Google Chat connection is in (managers only, while picking). */
export function useGoogleChatSpaces(labId: string, enabled: boolean) {
  return useQuery({
    queryKey: [...key(labId), "spaces"],
    queryFn: () => api<GoogleChatSpace[]>(`${base(labId)}spaces/`),
    enabled,
    retry: false,
  });
}
