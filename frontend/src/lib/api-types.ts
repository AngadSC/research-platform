// Hand-written from DECISIONS D35 and the allauth headless spec. Replace with generated OpenAPI types later.

export type Role = "pi" | "lab_admin" | "member" | "viewer";
export const ROLES: { value: Role; label: string }[] = [
  { value: "pi", label: "PI" },
  { value: "lab_admin", label: "Lab admin" },
  { value: "member", label: "Member" },
  { value: "viewer", label: "Viewer" },
];
export const roleLabel = (r: string) => ROLES.find((x) => x.value === r)?.label ?? r;

export interface User {
  id: string;
  email: string;
  display_name: string;
}
export interface Lab {
  id: string;
  name: string;
  institution: { id: string; name: string };
  my_role: Role;
  my_permissions: string[];
}
export interface Membership {
  id: string;
  user: User;
  role: Role;
  created_at: string;
}
export interface Invite {
  id: string;
  email: string;
  role: Role;
  expires_at: string;
  created_at: string;
  invited_by: User;
}
export interface InvitePreview {
  lab_name: string;
  role: Role;
  email: string;
}

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
