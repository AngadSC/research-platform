import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ChatMessage, ChatUnread } from "@/lib/api-types";

/** D206: chat polls while the tab is visible. Must match the list views' page_size. */
const POLL_MS = 4000;
const UNREAD_POLL_MS = 10000; // badges can lag a little; this runs on every page
export const CHAT_PAGE_SIZE = 100;
/** The key for the lab chat in `useUnreadChats`; the other keys are project ids. */
export const LAB_CHAT = "lab";

const lab = (labId: string) => `/api/labs/${labId}`;
/** No `projectId` means the lab's own chat. */
const url = (labId: string, projectId?: string) =>
  projectId ? `${lab(labId)}/projects/${projectId}/messages/` : `${lab(labId)}/chat/messages/`;
const messageUrl = (labId: string, projectId: string | undefined, id: string) =>
  projectId ? `${lab(labId)}/messages/${id}/` : `${lab(labId)}/chat/messages/${id}/`;
const reactUrl = (labId: string, projectId: string | undefined, id: string) =>
  `${messageUrl(labId, projectId, id)}reactions/`;
const unreadKey = (labId: string | undefined) => ["labs", labId, "chat-unread"];

/** Unread message counts for the lab: by project id, plus `LAB_CHAT`. Chats with none are missing. */
export function useUnreadChats(labId: string | undefined) {
  return useUnreadChatsQuery(labId).counts;
}

/** The same counts, plus whether the first answer has come (for telling new from already there). */
export function useUnreadChatsQuery(labId: string | undefined) {
  const { data = [], isSuccess } = useQuery({
    queryKey: unreadKey(labId),
    queryFn: () => api<ChatUnread[]>(`/api/labs/${labId}/chat/unread/`),
    enabled: !!labId,
    refetchInterval: UNREAD_POLL_MS,
  });
  return {
    counts: Object.fromEntries(data.map((r) => [r.project ?? LAB_CHAT, r.count])),
    isSuccess,
  };
}

/** The bell's "Mark all as read": marks every chat with new messages read, lab chat and projects. */
export function useMarkAllChatsRead(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (keys: string[]) => {
      const lastReadAt = new Date().toISOString();
      await Promise.all(
        keys.map((key) =>
          api(`${url(labId, key === LAB_CHAT ? undefined : key)}read/`, {
            method: "POST",
            body: { last_read_at: lastReadAt },
          }),
        ),
      );
    },
    onMutate: async () => {
      await qc.cancelQueries({ queryKey: unreadKey(labId) });
      qc.setQueryData<ChatUnread[]>(unreadKey(labId), []);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: unreadKey(labId) }),
  });
}

export function useChat(labId: string, projectId?: string) {
  const qc = useQueryClient();
  const key = projectId
    ? ["labs", labId, "projects", projectId, "messages"]
    : ["labs", labId, "chat", "messages"];
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
    mutationFn: (id: string) => api(messageUrl(labId, projectId, id), { method: "DELETE" }),
    onSuccess: refresh,
  });
  // D321: add or take away your emoji. The answer is the message with its new reactions.
  const react = useMutation({
    mutationFn: ({ id, emoji }: { id: string; emoji: string }) =>
      api<ChatMessage>(reactUrl(labId, projectId, id), { method: "POST", body: { emoji } }),
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
        rows?.filter((r) => r.project !== (projectId ?? null)),
      );
    },
    onSettled: () => qc.invalidateQueries({ queryKey: unreadKey(labId) }),
  });
  return { messages, send, remove, react, markRead: markRead.mutate };
}

/** The page of messages just before `iso`, oldest first. */
export const fetchOlderMessages = (labId: string, projectId: string | undefined, iso: string) =>
  api<ChatMessage[]>(`${url(labId, projectId)}?before=${encodeURIComponent(iso)}`);
