import { Badge, type BadgeVariant } from "@/components/ui/badge";

const TONES: Record<string, BadgeVariant> = {
  active: "success",
  approved: "success",
  complete: "success",
  completed: "success",
  published: "success",
  pending: "warning",
  in_review: "warning",
  running: "warning",
  expiring: "warning",
  draft: "secondary",
  archived: "secondary",
  rejected: "destructive",
  failed: "destructive",
  expired: "destructive",
};

/** Maps a backend status string to a tone; unknown statuses render neutral. */
export function StatusBadge({ status }: { status: string }) {
  const label = status.replace(/_/g, " ");
  return (
    <Badge variant={TONES[status.toLowerCase()] ?? "secondary"} className="capitalize">
      {label}
    </Badge>
  );
}
