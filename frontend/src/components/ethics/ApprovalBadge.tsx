import { Badge } from "@/components/ui/badge";
import { daysUntil, expiryTone, relativeDays } from "@/lib/ethics";

/** Status badge whose tone follows the expiry date. */
export function ApprovalBadge({ status, expiry }: { status: string; expiry: string }) {
  const days = daysUntil(expiry);
  return (
    <Badge variant={expiryTone(days, status)} className="capitalize" data-days={days}>
      {status}
    </Badge>
  );
}

export function ExpiryText({ expiry }: { expiry: string }) {
  return <span className="text-xs text-muted-foreground">{relativeDays(daysUntil(expiry))}</span>;
}
