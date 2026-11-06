import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ChatMessage, ChatUnread } from "@/lib/api-types";

/** D206: chat polls while the tab is visible. Must match ChatMessageListCreateView.page_size. */
const POLL_MS = 4000;
const UNREAD_POLL_MS = 15000; // badges can lag a little; this runs on every page
export const CHAT_PAGE_SIZE = 100;

const url = (labId: string, projectId: string) =>
  `/api/labs/${labId}/projects/${projectId}/messages/`;
const unreadKey = (labId: string | undefined) => ["labs", labId, "chat-unread"];

/** Unread message counts for the lab, by project id. Projects with none are missing. */
export function useUnreadChats(labId: string | undefined) {
  const { data = [] } = useQuery({
    queryKey: unreadKey(labId),
    queryFn: () => api<ChatUnread[]>(`/api/labs/${labId}/chat/unread/`),
    enabled: !!labId,
    refetchInterval: UNREAD_POLL_MS,
  });
  return Object.fromEntries(data.map((r) => [r.project, r.count]));
}

export function useChat(labId: string, projectId: string) {
  const qc = useQueryClient();
  const key = ["labs", labId, "projects", projectId, "messages"];
  const refresh = () => qc.invalidateQueries({ queryKey: key });
  const messages = useQuery({
    queryKey: key,
    queryFn: () => api<ChatMessage[]>(url(labId, projectId)),
    refetchInterval: POLL_MS,
  });
  const send = useMutation({
    mutationFn: (body: string) =>
      api<ChatMessage>(url(labId, projectId), { method: "POST", body: { body } }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/api/labs/${labId}/messages/${id}/`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  // Clears the badge at once; the refetch afterwards corrects it if anything newer arrived.
  const markRead = useMutation({
    mutationFn: (lastReadAt: string) =>
      api(`${url(labId, projectId)}read/`, {
        method: "POST",
        body: { last_read_at: lastReadAt },
      }),
    onMutate: async () => {
      await qc.cancelQueries({ queryKey: unreadKey(labId) });
      qc.setQueryData<ChatUnread[]>(unreadKey(labId), (rows) =>
        rows?.filter((r) => r.project !== projectId),
      );
    },
    onSettled: () => qc.invalidateQueries({ queryKey: unreadKey(labId) }),
  });
  return { messages, send, remove, markRead: markRead.mutate };
}

/** The page of messages just before `iso`, oldest first. */
export const fetchOlderMessages = (labId: string, projectId: string, iso: string) =>
  api<ChatMessage[]>(`${url(labId, projectId)}?before=${encodeURIComponent(iso)}`);
