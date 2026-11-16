import { cn } from "@/lib/utils";
import { Badge, type BadgeVariant } from "@/components/ui/badge";

const TONES: Record<string, BadgeVariant> = {
  active: "info",
  approved: "success",
  complete: "success",
  completed: "secondary",
  published: "success",
  pending: "warning",
  in_review: "warning",
  running: "info",
  expiring: "warning",
  paused: "warning",
  in_progress: "info",
  planning: "secondary",
  todo: "secondary",
  draft: "secondary",
  archived: "secondary",
  rejected: "destructive",
  failed: "destructive",
  expired: "destructive",
  error: "destructive",
  revoked: "secondary",
};

/** Maps a backend status string to a tone; unknown statuses render neutral. */
export function StatusBadge({ status }: { status: string }) {
  const label = status === "todo" ? "to do" : status.replace(/_/g, " ");
  return (
    <Badge
      variant={TONES[status.toLowerCase()] ?? "secondary"}
      className={cn(
        "capitalize",
        status.toLowerCase() === "completed" &&
          "bg-violet-100 text-violet-800 dark:bg-violet-500/20 dark:text-violet-200",
      )}
    >
      {label}
    </Badge>
  );
}
