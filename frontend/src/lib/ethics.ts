import type { BadgeVariant } from "@/components/ui/badge";
import type { ApprovalStatus } from "@/lib/api-types";
import { plural } from "@/lib/format";

export const WARN_DAYS = 60;
export const URGENT_DAYS = 7;
export const APPROVAL_STATUSES: { value: ApprovalStatus; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "active", label: "Active" },
  { value: "expired", label: "Expired" },
  { value: "withdrawn", label: "Withdrawn" },
];

/** Whole days from today (local) to an ISO date. Negative once past. */
export function daysUntil(iso: string, now: Date = new Date()): number {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const [y = 0, m = 1, d = 1] = iso.split("-").map(Number);
  return Math.round((new Date(y, m - 1, d).getTime() - today) / 86_400_000);
}

export function relativeDays(days: number): string {
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  if (days === -1) return "yesterday";
  return days > 0 ? `in ${plural(days, "day")}` : `${plural(-days, "day")} ago`;
}

/** Warn within 60 days; red within 7 days or once expired. Withdrawn approvals stay neutral. */
export function expiryTone(days: number, status: string): BadgeVariant {
  if (status === "withdrawn") return "secondary";
  if (status === "expired" || days < 0 || days <= URGENT_DAYS) return "destructive";
  if (days <= WARN_DAYS) return "warning";
  return status === "active" ? "success" : "secondary";
}

export const dayText = (iso: string | null) =>
  iso
    ? new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { dateStyle: "medium" })
    : "Not set";

export interface ApprovalValues {
  approval_number: string;
  board: string;
  title: string;
  approval_date: string;
  expiry_date: string;
}

/** Messages say what to do. ISO dates compare as strings. */
export function validateApproval(v: ApprovalValues): Record<string, string> {
  const e: Record<string, string> = {};
  if (!v.approval_number.trim()) e.approval_number = "Enter the approval number";
  if (!v.board.trim()) e.board = "Enter the ethics board";
  if (!v.title.trim()) e.title = "Enter a title";
  if (!v.approval_date) e.approval_date = "Pick the approval date";
  if (!v.expiry_date) e.expiry_date = "Pick the expiry date";
  else if (v.approval_date && v.expiry_date <= v.approval_date)
    e.expiry_date = "Expiry must be after the approval date";
  return e;
}
