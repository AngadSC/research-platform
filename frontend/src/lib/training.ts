import type { BadgeVariant } from "@/components/ui/badge";
import type { ComplianceStatus } from "@/lib/api-types";

export const CATEGORIES = [
  { value: "ethics", label: "Ethics" },
  { value: "safety", label: "Safety" },
  { value: "biosafety", label: "Biosafety" },
  { value: "chemical", label: "Chemical" },
  { value: "data_privacy", label: "Data and privacy" },
  { value: "equipment", label: "Equipment" },
  { value: "other", label: "Other" },
] as const;

export const APPLIES_TO = [
  { value: "all", label: "Everyone in the lab" },
  { value: "roles", label: "Certain roles" },
  { value: "projects", label: "People on certain projects" },
] as const;

export const ROLES = [
  { value: "pi", label: "PI" },
  { value: "lab_admin", label: "Lab admin" },
  { value: "member", label: "Member" },
  { value: "viewer", label: "Viewer" },
] as const;

export const STATUS: Record<ComplianceStatus, { label: string; tone: BadgeVariant }> = {
  done: { label: "Done", tone: "success" },
  expiring: { label: "Expiring", tone: "warning" },
  expired: { label: "Expired", tone: "destructive" },
  missing: { label: "Missing", tone: "outline" },
};

export const categoryLabel = (v: string) => CATEGORIES.find((c) => c.value === v)?.label ?? v;

export const validityText = (months: number | null) =>
  months === null ? "Never expires" : months % 12 === 0 ? `${months / 12} y` : `${months} mo`;
