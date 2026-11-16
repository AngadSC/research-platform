import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { GoogleChatSpace, GoogleChatStatus } from "@/lib/api-types";

/** The lab chat's link, or with `projectId` that project chat's (D318, D325). */
const base = (labId: string, projectId?: string) =>
  projectId
    ? `/api/labs/${labId}/projects/${projectId}/chat/google/`
    : `/api/labs/${labId}/chat/google/`;
/** The conversations your own connection is in: spaces, group chats and direct messages. */
export const spacesUrl = (labId: string, projectId?: string) =>
  projectId
    ? `/api/labs/${labId}/projects/${projectId}/chat/google/spaces/`
    : `/api/labs/${labId}/chat/google/spaces/`;
const key = (labId: string, projectId?: string) => [
  "labs",
  labId,
  "google-chat",
  projectId ?? "lab",
];

export const KIND_LABEL: Record<GoogleChatSpace["kind"], string> = {
  space: "Space",
  group_chat: "Group chat",
  direct_message: "Direct message",
};

/** Whether the chat is linked to a Google Chat conversation, and what you may do about it. */
export function useGoogleChat(labId: string, projectId?: string) {
  const qc = useQueryClient();
  const status = useQuery({
    queryKey: key(labId, projectId),
    queryFn: () => api<GoogleChatStatus>(base(labId, projectId)),
    enabled: !!labId,
  });
  const link = useMutation({
    mutationFn: (space: string) =>
      api<GoogleChatStatus>(base(labId, projectId), { method: "PUT", body: { space } }),
    onSuccess: (data) => qc.setQueryData(key(labId, projectId), data),
  });
  const unlink = useMutation({
    mutationFn: () => api(base(labId, projectId), { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(labId, projectId) }),
  });
  return { status, link, unlink };
}

export function useGoogleChatSpaces(labId: string, enabled: boolean, projectId?: string) {
  return useQuery({
    queryKey: [...key(labId, projectId), "spaces"],
    queryFn: () => api<GoogleChatSpace[]>(spacesUrl(labId, projectId)),
    enabled,
    retry: false,
  });
}
