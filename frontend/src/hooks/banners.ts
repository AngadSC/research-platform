import { useEffect, useRef } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { LAB_CHAT, useUnreadChatsQuery } from "@/hooks/chat";
import { useNotifications } from "@/hooks/ethics";
import { useProjects } from "@/hooks/projects";

/** How long a banner stays at the top of the page. */
export const BANNER_MS = 2000;

/** A banner at the top for two seconds whenever a new notification or chat message arrives.
 * What was already there when the page opened (or the lab changed) is not announced. */
export function useIncomingBanners(labId: string | undefined) {
  const navigate = useNavigate();
  const notifications = useNotifications(labId);
  const { counts: chats, isSuccess: chatsLoaded } = useUnreadChatsQuery(labId);
  const projects = useProjects(labId).data;

  const seenNotes = useRef<Set<string> | null>(null);
  const seenChats = useRef<Record<string, number> | null>(null);
  const lab = useRef(labId);

  useEffect(() => {
    if (lab.current !== labId) {
      lab.current = labId;
      seenNotes.current = null;
      seenChats.current = null;
    }
  }, [labId]);

  // Notifications: anything unread whose id was not there before.
  const data = notifications.data;
  useEffect(() => {
    if (!data || !labId) return;
    const unread = data.filter((n) => !n.read_at);
    if (seenNotes.current === null) {
      seenNotes.current = new Set(data.map((n) => n.id));
      return;
    }
    for (const n of unread) {
      if (seenNotes.current.has(n.id)) continue;
      toast(n.title, {
        description: n.body || undefined,
        duration: BANNER_MS,
        action: { label: "Open", onClick: () => void navigate(n.url) },
      });
    }
    seenNotes.current = new Set(data.map((n) => n.id));
  }, [data, labId, navigate]);

  // Chats: a count that went up since the last look.
  const counts = JSON.stringify(chats);
  const loaded = chatsLoaded;
  useEffect(() => {
    if (!labId || !loaded) return;
    const now = JSON.parse(counts) as Record<string, number>;
    const before = seenChats.current;
    seenChats.current = now;
    if (before === null) return;
    for (const [key, count] of Object.entries(now)) {
      if (count <= (before[key] ?? 0)) continue;
      const lab_ = key === LAB_CHAT;
      const name = lab_
        ? "Lab chat"
        : (projects?.find((p) => p.id === key)?.name ?? "Project chat");
      const to = lab_ ? `/labs/${labId}/chat` : `/labs/${labId}/projects/${key}?chat=1`;
      toast(`New message in ${name}`, {
        duration: BANNER_MS,
        action: { label: "Open", onClick: () => void navigate(to) },
      });
    }
  }, [counts, labId, loaded, projects, navigate]);
}
