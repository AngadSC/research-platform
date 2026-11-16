import { Bell, MessagesSquare } from "lucide-react";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { LAB_CHAT, useUnreadChats } from "@/hooks/chat";
import { useMarkRead, useNotifications } from "@/hooks/ethics";
import { useProjects } from "@/hooks/projects";
import { cn } from "@/lib/utils";
import { UnreadBadge } from "./UnreadBadge";

export function NotificationBell({ labId }: { labId: string }) {
  const { data = [] } = useNotifications(labId);
  const { one, all } = useMarkRead(labId);
  const unread = data.filter((n) => !n.read_at);
  const chats = useUnreadChats(labId);
  const projects = useProjects(labId).data ?? [];
  // Chats with something new, the lab chat first.
  const chatRows = Object.entries(chats)
    .filter(([, count]) => count > 0)
    .map(([key, count]) =>
      key === LAB_CHAT
        ? { key, count, name: "Lab chat", to: `/labs/${labId}/chat` }
        : {
            key,
            count,
            name: projects.find((p) => p.id === key)?.name ?? "Project chat",
            to: `/labs/${labId}/projects/${key}?chat=1`,
          },
    )
    .sort((a, b) => (a.key === LAB_CHAT ? -1 : b.key === LAB_CHAT ? 1 : 0));
  const messages = chatRows.reduce((n, r) => n + r.count, 0);
  const total = unread.length + messages;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={`Notifications, ${total} unread`}
        className="relative rounded-md p-1.5 text-muted-foreground hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none [&_svg]:size-4"
      >
        <Bell aria-hidden />
        <UnreadBadge count={total} className="absolute -top-1 -right-1" decorative />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between border-b px-3 py-2">
          <span className="text-sm font-semibold">Notifications</span>
          <Button
            variant="ghost"
            size="sm"
            disabled={unread.length === 0 || all.isPending}
            onClick={() => all.mutate()}
          >
            Mark all as read
          </Button>
        </div>
        {chatRows.length > 0 && (
          <ul aria-label="New chat messages" className="border-b">
            {chatRows.map((r) => (
              <li key={r.key} className="px-1 py-1">
                <DropdownMenuItem asChild className="flex items-center gap-2 px-2">
                  <Link to={r.to}>
                    <MessagesSquare aria-hidden className="size-4 shrink-0 text-primary" />
                    <span className="min-w-0 flex-1 truncate font-medium">{r.name}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {r.count} new {r.count === 1 ? "message" : "messages"}
                    </span>
                  </Link>
                </DropdownMenuItem>
              </li>
            ))}
          </ul>
        )}
        <ul className="max-h-80 overflow-y-auto">
          {unread.length === 0 && chatRows.length === 0 && (
            <li className="px-3 py-4 text-sm text-muted-foreground">You are all caught up.</li>
          )}
          {unread.slice(0, 8).map((n) => (
            <li key={n.id} className="grid gap-1 border-b px-1 py-1 last:border-b-0">
              {/* Every notification opens what it is about (a message, task, approval...). */}
              <DropdownMenuItem asChild className="grid gap-0.5 px-2">
                <Link to={n.url} onClick={() => one.mutate(n.id)}>
                  <span className="font-medium">{n.title}</span>
                  {n.body && (
                    <span className="line-clamp-2 text-xs text-muted-foreground">{n.body}</span>
                  )}
                </Link>
              </DropdownMenuItem>
              <div className="flex items-center justify-between px-2">
                <span className="text-xs text-muted-foreground">
                  <RelativeTime value={n.created_at} />
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Mark as read: ${n.title}`}
                  onClick={() => one.mutate(n.id)}
                >
                  Mark as read
                </Button>
              </div>
            </li>
          ))}
        </ul>
        <div className={cn("border-t px-3 py-2 text-sm")}>
          <Link to={`/labs/${labId}/notifications`} className="text-primary hover:underline">
            See all notifications
          </Link>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
