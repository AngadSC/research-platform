// Aliases over the backend OpenAPI types (regenerate with `make types`).
// allauth headless types are not in the DRF schema, so they stay hand-written below.
import type { components } from "@/lib/api-schema";

type Schemas = components["schemas"];

export type Role = Schemas["RoleEnum"];
export const ROLES: { value: Role; label: string }[] = [
  { value: "pi", label: "PI" },
  { value: "lab_admin", label: "Lab admin" },
  { value: "member", label: "Member" },
  { value: "viewer", label: "Viewer" },
];
export const roleLabel = (r: string) => ROLES.find((x) => x.value === r)?.label ?? r;

export type User = Schemas["User"];
export type Lab = Schemas["Lab"];
export type Membership = Schemas["Membership"];
export type Invite = Schemas["Invite"];
export type InvitePreview = Schemas["InvitePreview"];
export type AuditEvent = Schemas["AuditEvent"];
export type AuditPage = Schemas["PaginatedAuditEventList"];

// allauth headless envelope
export interface AuthFlow {
  id: string;
  is_pending?: boolean;
}
export interface AuthEnvelope {
  status: number;
  data?: {
    user?: { id: string | number; email?: string; display?: string };
    flows?: AuthFlow[];
    [k: string]: unknown;
  };
  meta?: { is_authenticated?: boolean; secret?: string; [k: string]: unknown };
  errors?: { message: string; code?: string; param?: string }[];
}
export interface TotpAuthenticator {
  type: "totp";
  created_at: number;
  last_used_at: number | null;
}
export interface RecoveryCodes {
  type: "recovery_codes";
  total_code_count: number;
  unused_code_count: number;
  unused_codes?: string[];
}
