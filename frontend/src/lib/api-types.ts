// Aliases over the backend OpenAPI types (regenerate with `make types`).
// allauth headless types are not in the DRF schema, so they stay hand-written below.
import type { components } from "@/lib/api-schema";

type Schemas = components["schemas"];

export type Role = Schemas["LabRoleEnum"];
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
export type Project = Schemas["Project"];
export type ProjectInput = Schemas["ProjectInput"];
export type ProjectStatus = Schemas["ProjectStatusEnum"];
export type ProjectRole = Schemas["ProjectRoleEnum"];
export type ProjectMembership = Schemas["ProjectMembership"];
export type Deadline = Schemas["Deadline"];
export type DeadlineInput = Schemas["DeadlineInput"];
export type Task = Schemas["Task"];
export type TaskInput = Schemas["TaskInput"];
export type Attachment = Schemas["Attachment"];
export type AttachmentRef = Schemas["AttachmentRef"];
export type TaskStatus = Schemas["TaskStatusEnum"];
export type DocumentRow = Schemas["DocumentList"];
export type DocumentFull = Schemas["Document"];
export type DocumentSaveInput = Schemas["DocumentSave"];
export type DocumentConflict = Schemas["Conflict"];
export type RevisionRow = Schemas["RevisionList"];
export type Revision = Schemas["Revision"];
export type Lineage = Schemas["Lineage"];
export type LineageNode = Schemas["LineageNode"];
export type LineageEdge = Schemas["LineageEdge"];
export type LineageKind = Schemas["LineageKindEnum"];
export type Dataset = Schemas["Dataset"];
export type DatasetRef = Schemas["DatasetRef"];
export type Analysis = Schemas["Analysis"];
export type ResearchResult = Schemas["Result"];
export type Decision = Schemas["Decision"];
export type Reference = Schemas["Reference"];
export type SearchHit = Schemas["SearchHit"];
export type Manuscript = Schemas["Manuscript"];
export type ConnectedAccount = Schemas["ConnectedAccount"];
export type IntegrationProvider = Schemas["Provider"];
export type PickerToken = Schemas["PickerToken"];
export type ConnectOutput = Schemas["ConnectOutput"];
export type ExternalLink = Schemas["ExternalLink"];
export type ExternalLinkInput = Schemas["ExternalLinkInput"];
export type Handover = Schemas["Handover"];
export type HandoverItem = Schemas["HandoverItem"];
export type ManuscriptStatus = Schemas["ManuscriptStatusEnum"];

export const PROJECT_STATUSES: { value: ProjectStatus; label: string }[] = [
  { value: "planning", label: "Planning" },
  { value: "active", label: "Active" },
  { value: "paused", label: "Paused" },
  { value: "completed", label: "Completed" },
  { value: "archived", label: "Archived" },
];
export const PROJECT_ROLES: { value: ProjectRole; label: string }[] = [
  { value: "lead", label: "Lead" },
  { value: "contributor", label: "Contributor" },
  { value: "viewer", label: "Viewer" },
];
export const TASK_STATUSES: { value: TaskStatus; label: string }[] = [
  { value: "todo", label: "To do" },
  { value: "in_progress", label: "In progress" },
  { value: "done", label: "Done" },
];
export const taskStatusLabel = (s: string) => TASK_STATUSES.find((x) => x.value === s)?.label ?? s;
export const personName = (u: { display_name?: string; email: string }) =>
  u.display_name || u.email;

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
    user?: {
      id: string | number;
      email?: string;
      display?: string;
      has_usable_password?: boolean;
    };
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

export type EthicsApproval = Schemas["EthicsApproval"];
export type EthicsApprovalInput = Schemas["EthicsApprovalInput"];
export type ApprovalStatus = Schemas["ApprovalStatusEnum"];
export type AppNotification = Schemas["Notification"];
export type RetentionItem = Schemas["RetentionItem"];
