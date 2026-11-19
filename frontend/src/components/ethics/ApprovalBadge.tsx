import { Badge } from "@/components/ui/badge";
import type { EthicsApproval } from "@/lib/api-types";
import { daysUntil, expiryTone, expiryWarning, relativeDays } from "@/lib/ethics";
import { plural } from "@/lib/format";

/** Status badge: green while active, red once expired. */
export function ApprovalBadge({ status, expiry }: { status: string; expiry: string | null }) {
  const days = expiry ? daysUntil(expiry) : 0;
  return (
    <Badge variant={expiry ? expiryTone(days, status) : "secondary"} className="capitalize">
      {status}
    </Badge>
  );
}

/** Time left. Within 30 days it is a warning, unless a renewal is already on file. */
export function ExpiryText({
  expiry,
  status = "active",
  renewal = null,
}: {
  expiry: string | null;
  status?: string;
  renewal?: EthicsApproval["renewal_status"];
}) {
  if (!expiry) return null;
  const days = daysUntil(expiry);
  const warn = expiryWarning(days, status);
  if (warn && renewal)
    return (
      <Badge variant="secondary">{renewal === "pending" ? "Renewal pending" : "Renewed"}</Badge>
    );
  if (warn)
    return (
      <Badge variant={warn}>
        {days === 0 ? "Expires today" : `Expires in ${plural(days, "day")}`}
      </Badge>
    );
  return <span className="text-xs text-muted-foreground">{relativeDays(days)}</span>;
}
