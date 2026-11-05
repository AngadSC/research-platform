import { useNotifications } from "@/hooks/ethics";
import { cn } from "@/lib/utils";

/** Unread in-app notifications for a lab; shares the notifications query, so reading one updates every badge. */
// eslint-disable-next-line react-refresh/only-export-components
export function useUnreadCount(labId: string | undefined) {
  const { data = [] } = useNotifications(labId);
  return data.filter((n) => !n.read_at).length;
}

/** Red count bubble, capped at 99+. Renders nothing at zero. */
export function UnreadBadge({ count, className }: { count: number; className?: string }) {
  if (count <= 0) return null;
  return (
    <span
      role="img"
      data-testid="unread-count"
      aria-label={`${count} unread ${count === 1 ? "notification" : "notifications"}`}
      className={cn(
        "grid h-4 min-w-4 place-items-center rounded-full bg-danger px-1 text-[10px] leading-none font-bold text-danger-foreground",
        className,
      )}
    >
      {count > 99 ? "99+" : count}
    </span>
  );
}
