// Aliases over the backend OpenAPI types (regenerate with `make types`).
// allauth headless types are not in the DRF schema, so they stay hand-written below.
import type { components } from "@/lib/api-schema";

type Schemas = components["schemas"];

export type Role = Schemas["LabRoleEnum"];
export const ROLES: { value: Role; label: string; help: string }[] = [
  {
    value: "pi",
    label: "PI",
    help: "Runs the lab. Can change anything, and is the only role that sees funding.",
  },
  {
    value: "lab_admin",
    label: "Lab admin",
    help: "Helps run the lab. Sees every project and manages members, but not funding or billing.",
  },
  {
    value: "member",
    label: "Member",
    help: "Works in the lab. Sees projects they are added to and can start their own.",
  },
  {
    value: "viewer",
    label: "Viewer",
    help: "Can read the lab and projects they are added to, but not change their work.",
  },
];
export const roleLabel = (r: string) => ROLES.find((x) => x.value === r)?.label ?? r;

export type User = Schemas["User"];
export type Me = Schemas["Me"];
export type LoginMethods = Schemas["LoginMethods"];
export type Lab = Schemas["Lab"];
export type Membership = Schemas["Membership"];
export type Invite = Schemas["Invite"];
export type InvitePreview = Schemas["InvitePreview"];
export type Project = Schemas["Project"];
export type ProjectInput = Schemas["ProjectCreate"];
export type ProjectStatus = Schemas["ProjectStatusEnum"];
export type ProjectRole = Schemas["ProjectRoleEnum"];
export type ProjectMembership = Schemas["ProjectMembership"];
export type Deadline = Schemas["Deadline"];
export type DeadlineInput = Schemas["DeadlineInput"];
export type Task = Schemas["Task"];
export type MyTask = Schemas["MyTask"];
export type TaskInput = Schemas["TaskInput"];
export type ChatMessage = Schemas["ChatMessage"];
export type ChatUnread = Schemas["ChatUnread"];
export type TaskPost = Schemas["TaskPost"];
export type TaskDocument = Schemas["TaskDocument"];
export type TaskAttachment = Schemas["TaskAttachment"];
export type TaskView = "board" | "list";
export type Attachment = Schemas["Attachment"];
export type AttachmentRef = Schemas["AttachmentRef"];
export type TaskStatus = Schemas["TaskStatusEnum"];
export type DocumentRow = Schemas["DocumentList"];
export type DocumentFull = Schemas["Document"];
export type DocumentSaveInput = Schemas["DocumentSave"];
export type Folder = Schemas["Folder"];
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
export type InstitutionHit = Schemas["InstitutionHit"];
export type ExternalLinkInput = Schemas["ExternalLinkInput"];
export type ItemSearchResult = Schemas["ItemSearchResult"];
export type ImportResult = Schemas["ImportResult"];
export type TaskSource = Schemas["TaskSource"];
export type ZoteroItem = Schemas["ZoteroItem"];
export type Webhook = Schemas["Webhook"];
export type WebhookCreated = Schemas["WebhookCreated"];
export type WebhookEvent = Schemas["WebhookEvent"];
export type WebhookList = Schemas["WebhookList"];
export type WebhookTestResult = Schemas["WebhookTestResult"];
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
export const PROJECT_ROLES: { value: ProjectRole; label: string; help: string }[] = [
  {
    value: "lead",
    label: "Lead",
    help: "Runs the project. Can edit everything and choose who is on it.",
  },
  { value: "contributor", label: "Contributor", help: "Can add and edit the project's work." },
  { value: "viewer", label: "Viewer", help: "Can see the project but not change its work." },
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

// Admin area (Run 4)
export type Protocol = Schemas["Protocol"];
export type ProtocolInput = Schemas["ProtocolInput"];
export type InventoryUsage = Schemas["InventoryUsage"];
export type InventoryImportResult = Schemas["InventoryImportResult"];
export type InventoryItem = Schemas["Inventory"];
export type InventoryInput = Schemas["InventoryInput"];
export type InventoryOrder = Schemas["InventoryOrder"];
export type InventoryOrderInput = Schemas["InventoryOrderInput"];
export type OrderStatus = InventoryOrder["status"];
export type CalendarItem = Schemas["CalendarItem"];
export type LabEvent = Schemas["LabEvent"];
export type LabEventInput = Schemas["LabEventInput"];
export type Meeting = Schemas["Meeting"];
export type MeetingInput = Schemas["MeetingInput"];
export type CalendarFeedStatus = Schemas["CalendarFeedStatus"];
export type GoogleEvent = Schemas["GoogleEvent"];
export type GoogleCalendarSync = Schemas["GoogleCalendarSync"];
export type GoogleCalendarSyncInput = Schemas["PatchedGoogleCalendarSyncInput"];
export type SyncResult = Schemas["SyncResult"];
export type VideoOptions = Schemas["VideoOptions"];
export type CalendarFeedCreated = Schemas["CalendarFeedCreated"];
export type OnboardingItem = Schemas["OnboardingItem"];
export type OnboardingItemInput = Schemas["OnboardingItemInput"];
export type InstitutionResource = Schemas["Resource"];
export type InstitutionResourceInput = Schemas["ResourceInput"];
export type ResourceCategory = InstitutionResourceInput["category"];
export const RESOURCE_CATEGORIES: { value: ResourceCategory; label: string }[] = [
  { value: "ethics", label: "Ethics" },
  { value: "funding", label: "Funding" },
  { value: "data_management", label: "Data management" },
  { value: "other", label: "Other" },
];

// Project workflow (Run 4)
export type Funding = Schemas["Funding"];
export type FundingInput = Schemas["FundingInput"];
export type ExternalOutput = Schemas["ExternalOutput"];
export type ExternalOutputInput = Schemas["ExternalOutputInput"];
export type WorkflowProgress = Schemas["WorkflowProgress"];
export type ReviewItem = Schemas["ReviewItem"];
export type ReviewItemInput = Schemas["ReviewItemInput"];
export type RecruitmentEntry = Schemas["RecruitmentEntry"];
export type RecruitmentEntryInput = Schemas["RecruitmentEntryInput"];
export type RecruitmentPlan = Schemas["RecruitmentPlan"];
export type DeadlinePriority = Schemas["PriorityEnum"];

// Data management plan (Run 5, D180-D182)
export type Dmp = Schemas["Dmp"];
export type DmpInput = Schemas["PatchedDmpInput"];
export type DmpRevision = Schemas["DmpRevision"];

// Training (Run 5, D175-D179)
export type TrainingRequirement = Schemas["TrainingRequirement"];
export type TrainingRequirementInput = Schemas["TrainingRequirementInput"];
export type TrainingRecord = Schemas["TrainingRecord"];
export type TrainingRecordInput = Schemas["TrainingRecordCreate"];
export type TrainingCompliance = Schemas["TrainingCompliance"];
export type TrainingCell = Schemas["TrainingCell"];
export type TrainingExpiring = Schemas["Expiring"];
export type ComplianceStatus = Schemas["ComplianceStatusEnum"];
// Paper library
export type Paper = Schemas["Paper"];
export type PaperDetail = Schemas["PaperDetail"];
export type PaperInput = Schemas["PaperInput"];
export type PaperNote = Schemas["PaperNote"];
export type PaperCitations = Schemas["PaperCitation"];
export type PaperDoiLookup = Schemas["PaperDoiLookup"];
