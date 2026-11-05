import { plural } from "@/lib/format";

/** A count pill that also reads out as "3 unread messages". Renders nothing at zero. */
export function UnreadBadge({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span className="ml-auto shrink-0 rounded-full bg-destructive px-1.5 text-xs font-bold text-destructive-foreground">
      <span aria-hidden>{count > 99 ? "99+" : count}</span>
      <span className="sr-only">{plural(count, "unread message")}</span>
    </span>
  );
}
