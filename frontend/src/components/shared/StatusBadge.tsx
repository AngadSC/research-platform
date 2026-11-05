import { Badge, type BadgeVariant } from "@/components/ui/badge";

const TONES: Record<string, BadgeVariant> = {
  active: "success",
  approved: "success",
  complete: "success",
  completed: "success",
  done: "success",
  published: "success",
  pending: "warning",
  in_review: "warning",
  running: "warning",
  expiring: "warning",
  paused: "warning",
  in_progress: "warning",
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

const statusLabel = (status: string) => (status === "todo" ? "to do" : status.replace(/_/g, " "));

/** Maps a backend status string to a tone; unknown statuses render neutral. */
export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant={TONES[status.toLowerCase()] ?? "secondary"} className="capitalize">
      {statusLabel(status)}
    </Badge>
  );
}

/** For a coloured banner: a plain white pill in the banner's own colour. */
export function StatusPill({ status, className }: { status: string; className: string }) {
  return (
    <Badge variant="outline" className={`border-transparent bg-on-vivid capitalize ${className}`}>
      {statusLabel(status)}
    </Badge>
  );
}
