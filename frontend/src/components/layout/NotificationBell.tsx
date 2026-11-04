import { Bell } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { notificationLink, useMarkRead, useNotifications } from "@/hooks/ethics";
import { when } from "@/lib/format";
import { cn } from "@/lib/utils";

export function NotificationBell({ labId }: { labId: string }) {
  const { data = [] } = useNotifications(labId);
  const { one, all } = useMarkRead(labId);
  const navigate = useNavigate();
  const unread = data.filter((n) => !n.read_at);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={`Notifications, ${unread.length} unread`}
        className="relative rounded-md p-1.5 text-muted-foreground hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none [&_svg]:size-4"
      >
        <Bell aria-hidden />
        {unread.length > 0 && (
          <span
            data-testid="unread-count"
            className="absolute -top-1 -right-1 grid min-w-4 place-items-center rounded-full bg-primary px-1 text-[10px] font-medium text-primary-foreground"
          >
            {unread.length}
          </span>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-80 p-0">
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
        <ul className="max-h-80 overflow-y-auto">
          {unread.length === 0 && (
            <li className="px-3 py-4 text-sm text-muted-foreground">You are all caught up.</li>
          )}
          {unread.slice(0, 8).map((n) => (
            <li key={n.id} className="grid gap-1 border-b px-3 py-2 last:border-b-0">
              <button
                type="button"
                className="text-left text-sm font-medium hover:underline"
                onClick={() => {
                  one.mutate(n.id);
                  void navigate(notificationLink(labId, n));
                }}
              >
                {n.title}
              </button>
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">{when(n.created_at)}</span>
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
