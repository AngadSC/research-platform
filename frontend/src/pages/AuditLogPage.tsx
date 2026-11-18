import { ScrollText, ShieldAlert } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useParams, useSearchParams } from "react-router";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { DetailPanel } from "@/components/shared/DetailPanel";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAuditEvents, useLab, useMembers, type AuditFilters } from "@/hooks/workspace";
import { ApiError } from "@/lib/api";
import { fullDate } from "@/lib/format";
import type { AuditEvent } from "@/lib/api-types";

const ACTIONS: Record<AuditEvent["action"], string> = {
  "auth.login": "Signed in",
  "auth.login_failed": "Failed sign-in attempt",
  "auth.logout": "Signed out",
  "auth.password_changed": "Changed a password",
  "auth.mfa_enabled": "Turned on two-step verification",
  "auth.mfa_disabled": "Turned off two-step verification",
  "auth.social_connected": "Connected a sign-in account",
  "auth.social_disconnected": "Disconnected a sign-in account",
  "auth.email_added": "Added an email address",
  "auth.email_removed": "Removed an email address",
  "lab.created": "Created the lab",
  "lab.updated": "Updated the lab",
  "membership.invited": "Invited a member",
  "membership.invite_revoked": "Revoked an invitation",
  "membership.invite_accepted": "Accepted an invitation",
  "membership.invite_role_changed": "Changed an invitation's role",
  "membership.invite_resent": "Sent an invitation again",
  "membership.role_changed": "Changed a member's role",
  "membership.removed": "Removed a member",
  "project_membership.added": "Added someone to a project",
  "project_membership.role_changed": "Changed a project role",
  "project_membership.removed": "Removed someone from a project",
  "project.created": "Created a project",
  "project.updated": "Updated a project",
  "project.archived": "Archived a project",
  "project.deleted": "Deleted a project",
  "project.exported": "Exported a project",
  "document.created": "Created a document",
  "document.viewed": "Viewed a document",
  "document.restored": "Restored a document",
  "document.deleted": "Deleted a document",
  "document.owner_changed": "Gave a document a new owner",
  "attachment.uploaded": "Uploaded a file",
  "attachment.downloaded": "Downloaded a file",
  "attachment.deleted": "Deleted a file",
  "task.deleted": "Deleted a task",
  "task.unassigned": "Unassigned a task",
  "task_post.deleted": "Deleted a task update",
  "chat_message.deleted": "Deleted a chat message",
  "deadline.deleted": "Deleted a deadline",
  "dataset.created": "Added a dataset",
  "dataset.updated": "Updated a dataset",
  "dataset.deleted": "Deleted a dataset",
  "analysis.created": "Added an analysis",
  "analysis.updated": "Updated an analysis",
  "analysis.deleted": "Deleted an analysis",
  "result.created": "Added a result",
  "result.updated": "Updated a result",
  "result.deleted": "Deleted a result",
  "decision.created": "Added a decision",
  "decision.updated": "Updated a decision",
  "decision.deleted": "Deleted a decision",
  "manuscript.created": "Added a manuscript",
  "manuscript.updated": "Updated a manuscript",
  "manuscript.deleted": "Deleted a manuscript",
  "ethics_approval.created": "Added an ethics approval",
  "ethics_approval.updated": "Updated an ethics approval",
  "ethics_approval.links_changed": "Changed what an ethics approval is connected to",
  "ethics_approval.deleted": "Deleted an ethics approval",
  "retention.changed": "Changed how long project data is kept",
  "audit_log.viewed": "Viewed the audit log",
  "handover.generated": "Opened a handover",
  "integration.connected": "Connected an outside service",
  "integration.disconnected": "Disconnected an outside service",
  "integration.revoked": "Removed someone's connected service",
  "integration.refresh_failed": "A connected service stopped working",
  "integration.picker_token_issued": "Opened the Google Drive file picker",
  "integration.searched": "Searched a connected service",
  "external_link.created": "Linked an outside item",
  "external_link.removed": "Removed a link to an outside item",
  "external_link.change_accepted": "Accepted a change to a linked item",
  "inventory_item.created": "Added an inventory item",
  "inventory_item.updated": "Updated an inventory item",
  "inventory_item.deleted": "Deleted an inventory item",
  "inventory.exported": "Exported the inventory",
  "inventory.imported": "Imported inventory from a file",
  "inventory.used": "Took stock from an inventory item",
  "notebook.created": "Wrote a notebook entry",
  "notebook.updated": "Edited a notebook entry",
  "notebook.deleted": "Deleted a notebook entry",
  "notebook.locked": "Locked a notebook entry",
  "notebook.exported": "Exported a notebook",
  "subject.created": "Added a subject",
  "subject.updated": "Edited a subject",
  "subject.deleted": "Deleted a subject",
  "inventory.use_reversed": "Undid taking reagent out of stock",
  "protocol.created": "Added a protocol",
  "protocol.updated": "Updated a protocol",
  "protocol.deleted": "Deleted a protocol",
  "inventory_order.created": "Added an order",
  "inventory_order.updated": "Updated an order",
  "lab_event.created": "Added a calendar event",
  "lab_event.updated": "Updated a calendar event",
  "meeting.created": "Added a meeting",
  "meeting.updated": "Changed a meeting",
  "meeting.deleted": "Deleted a meeting",
  "calendar_feed.created": "Made a calendar link",
  "google_chat.linked": "Linked a chat to Google Chat",
  "google_chat.unlinked": "Stopped syncing a chat with Google Chat",
  "google_chat.imported": "Imported messages from Google Chat",
  "calendar_feed.revoked": "Turned off a calendar link",
  "lab_event.deleted": "Deleted a calendar event",
  "onboarding_item.created": "Added an onboarding item",
  "onboarding_item.updated": "Updated an onboarding item",
  "onboarding_item.deleted": "Deleted an onboarding item",
  "onboarding.completion_changed": "Ticked or unticked an onboarding item",
  "institution_resource.created": "Added an institution resource",
  "institution_resource.updated": "Updated an institution resource",
  "institution_resource.deleted": "Deleted an institution resource",
  "funding.created": "Added funding",
  "funding.updated": "Updated funding",
  "funding.deleted": "Deleted funding",
  "external_output.created": "Added a poster, talk or conference",
  "external_output.updated": "Updated a poster, talk or conference",
  "external_output.deleted": "Deleted a poster, talk or conference",
  "review_item.created": "Added a review item",
  "review_item.updated": "Updated a review item",
  "review_item.deleted": "Deleted a review item",
  "recruitment_entry.created": "Added a recruitment entry",
  "recruitment_entry.updated": "Updated a recruitment entry",
  "recruitment_entry.deleted": "Deleted a recruitment entry",
  "recruitment_plan.updated": "Updated a recruitment plan",
  "participant.created": "Added participants",
  "participant.updated": "Updated a participant",
  "participant.archived": "Archived a participant",
  "participant.restored": "Restored a participant",
  "participant_component.created": "Added a participant data column",
  "participant_component.updated": "Updated a participant data column",
  "participant_component.deleted": "Deleted a participant data column",
  "participant_cell.changed": "Changed a participant data cell",
  "participant_file.added": "Linked a file to a participant cell",
  "participant_file.changed": "Changed a participant file link",
  "participant_file.removed": "Removed a participant file link",
  "participant_reason.changed": "Changed the reasons for missing data",
  "participant.imported": "Imported participants from a sheet",
  "participant.import_undone": "Undid a participant import",
  "participant.files_matched": "Matched files to participants",
  "participant.links_checked": "Checked participant file links",
  "participant.tasks_created": "Created tasks from participant gaps",
  "participant_rule.saved": "Saved a participant inclusion rule",
  "participant_rule.archived": "Removed a participant inclusion rule",
  "participant_set.locked": "Locked a set of participants for an analysis",
  "participant_flow.exported": "Exported the participant flow summary",
  "participant.identifier_blocked": "Blocked a name or contact detail from the registry",
  "ai_access.granted": "Gave an AI app access",
  "ai_access.revoked": "Removed an AI app's access",
  "ai_tool.write": "An AI app made a change",
  "ai_key.saved": "Saved an assistant API key",
  "ai_key.removed": "Removed an assistant API key",
  "lab_ai_key.set": "Set the lab's AI key",
  "lab_ai_key.replaced": "Replaced the lab's AI key",
  "lab_ai_key.removed": "Removed the lab's AI key",
  "lab_ai_key.cap_changed": "Changed the lab's monthly AI limit",
  "training_requirement.created": "Added a training requirement",
  "training_requirement.updated": "Updated a training requirement",
  "training_requirement.deleted": "Deleted a training requirement",
  "training_record.created": "Added a training record",
  "training_record.updated": "Updated a training record",
  "training_record.verified": "Verified a training record",
  "training_record.deleted": "Deleted a training record",
  "training.reminded": "Sent a training reminder",
  "dmp.created": "Added a data management plan",
  "dmp.updated": "Updated a data management plan",
  "dmp.approved": "Approved a data management plan",
  "dmp.deleted": "Deleted a data management plan",
  "paper.deleted": "Deleted a paper",
  "paper_note.deleted": "Deleted a paper note",
  "webhook.created": "Added a webhook",
  "webhook.updated": "Changed a webhook",
  "webhook.deleted": "Removed a webhook",
  "tasks.imported": "Imported tasks",
  "papers.imported": "Imported papers",
  "folder.participant_flag_changed": "Changed a folder's identifying mark",
  "document.participant_flag_changed": "Changed a document's identifying mark",
  "attachment.participant_flag_changed": "Changed a file's identifying mark",
  "dataset.participant_flag_changed": "Changed a dataset's identifying mark",
  "file_link.created": "Made a download or upload link for a file",
};
const humanKey = (k: string) => k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
// An action newer than this page still reads as words, never as a code.
const actionLabel = (a: string) =>
  ACTIONS[a as AuditEvent["action"]] ?? humanKey(a.replace(".", " "));
/** The action in words; an import says how many items it added. */
const actionText = (e: AuditEvent) => {
  const rows = (e.metadata as { rows?: unknown } | null)?.rows;
  if (e.action === "inventory.imported" && typeof rows === "number")
    return `Imported ${rows} ${rows === 1 ? "item" : "items"}`;
  return actionLabel(e.action);
};
const who = (e: AuditEvent) => e.actor?.display_name || e.actor?.email || "System";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const isId = (v: unknown): boolean =>
  (typeof v === "string" && UUID.test(v)) || (Array.isArray(v) && v.length > 0 && v.every(isId));
/** "labs.InventoryItem" reads "Inventory item". */
const typeWord = (t: string) =>
  humanKey((t.split(".").pop() ?? t).replace(/([a-z])([A-Z])/g, "$1 $2").toLowerCase());
/** "8.000000" reads "8"; lists read as words. */
const show = (v: unknown): string => {
  if (typeof v === "string") return /^-?\d+\.\d+$/.test(v) ? String(Number(v)) : v;
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (Array.isArray(v))
    return v.map((x) => (typeof x === "string" ? x.replace(/_/g, " ") : show(x))).join(", ");
  return JSON.stringify(v);
};

/** The event's details as a reader wants them: ids left out (the target already names the
 * thing), an amount with its unit, and what left the item only when it differs from that. */
function details(meta: Record<string, unknown>): [string, string][] {
  const unit = typeof meta.unit === "string" && "amount" in meta ? meta.unit : "";
  return Object.entries(meta)
    .filter(
      ([k, v]) => !isId(v) && !(k === "unit" && unit) && !(k === "deducted" && v === meta.amount),
    )
    .map(([k, v]) => [
      k === "deducted" ? "Taken off the item" : humanKey(k),
      k === "amount" && unit ? `${show(v)} ${unit}` : show(v),
    ]);
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

/** Relative time, with the exact local time under it (and on hover). */
function When({ value }: { value: string }) {
  return (
    <span className="grid">
      <RelativeTime value={value} />
      <span className="text-xs text-muted-foreground">{fullDate(value)}</span>
    </span>
  );
}

function EventDetails({ e }: { e: AuditEvent }) {
  const meta =
    e.metadata && typeof e.metadata === "object" && !Array.isArray(e.metadata)
      ? details(e.metadata as Record<string, unknown>)
      : [];
  return (
    <dl className="grid gap-4 py-4">
      <Field label="When">
        <When value={e.created_at} />
      </Field>
      <Field label="Who">{who(e)}</Field>
      <Field label="Action">{actionText(e)}</Field>
      <Field label={e.target_type ? typeWord(e.target_type) : "Target"}>
        {cleanTarget(e.target_label)}
      </Field>
      {meta.length > 0 && (
        <Field label="Details">
          <dl className="grid gap-2 rounded-md border p-3">
            {meta.map(([k, v]) => (
              <Field key={k} label={k}>
                {v}
              </Field>
            ))}
          </dl>
        </Field>
      )}
    </dl>
  );
}

const columns: Column<AuditEvent>[] = [
  {
    key: "when",
    header: "When",
    cell: (e) => <When value={e.created_at} />,
  },
  { key: "who", header: "Who", cell: who },
  { key: "action", header: "Action", cell: (e) => actionText(e) },
  { key: "target", header: "Target", cell: (e) => cleanTarget(e.target_label) },
];

const ALL = "all";

export function AuditLogPage() {
  const { labId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const { data: lab } = useLab(labId);
  const allowed = lab?.my_permissions.includes("view_audit_log");
  const members = useMembers(labId);
  const filters: AuditFilters = {
    action: params.get("action") ?? undefined,
    actor: params.get("actor") ?? undefined,
    date_from: params.get("date_from") ?? undefined,
    date_to: params.get("date_to") ?? undefined,
  };
  // Changes by default; views and downloads only when asked for (or when picked as the action).
  const withReads = params.get("reads") === "1";
  const events = useAuditEvents(
    labId,
    { ...filters, changes_only: withReads || filters.action ? undefined : "true" },
    !!allowed,
  );
  const [open, setOpen] = useState<AuditEvent | null>(null);

  const set = (key: string, value: string) =>
    setParams(
      (p) => {
        const n = new URLSearchParams(p);
        if (value && value !== ALL) n.set(key, value);
        else n.delete(key);
        return n;
      },
      { replace: true },
    );

  const header = (
    <PageHeader title="Audit log" description={lab ? `Who did what in ${lab.name}.` : undefined} />
  );

  const denied =
    (lab && !allowed) || (events.error instanceof ApiError && events.error.status === 403);
  if (denied)
    return (
      <>
        {header}
        <EmptyState
          icon={ShieldAlert}
          title="You don't have access to the audit log"
          description="Only PIs and lab admins can see the audit log. Ask one of them if you need something from it."
        />
      </>
    );

  const rows = events.data?.pages.flatMap((p) => p.results) ?? [];
  const filtered = Object.values(filters).some(Boolean);

  return (
    <>
      {header}
      <div className="mb-6 flex flex-wrap items-end gap-3">
        <div className="grid gap-1.5">
          <label className="text-sm font-medium" htmlFor="audit-action">
            Action
          </label>
          <Select value={filters.action ?? ALL} onValueChange={(v) => set("action", v)}>
            <SelectTrigger id="audit-action" className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All actions</SelectItem>
              {Object.entries(ACTIONS).map(([code, label]) => (
                <SelectItem key={code} value={code}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-1.5">
          <label className="text-sm font-medium" htmlFor="audit-actor">
            Person
          </label>
          <Select value={filters.actor ?? ALL} onValueChange={(v) => set("actor", v)}>
            <SelectTrigger id="audit-actor" className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Everyone</SelectItem>
              {(members.data ?? []).map((m) => (
                <SelectItem key={m.user.id} value={m.user.id}>
                  {m.user.display_name || m.user.email}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-1.5">
          <label className="text-sm font-medium" htmlFor="audit-from">
            From
          </label>
          <Input
            id="audit-from"
            type="date"
            className="w-40"
            value={filters.date_from ?? ""}
            onChange={(e) => set("date_from", e.target.value)}
          />
        </div>
        <div className="grid gap-1.5">
          <label className="text-sm font-medium" htmlFor="audit-to">
            To
          </label>
          <Input
            id="audit-to"
            type="date"
            className="w-40"
            value={filters.date_to ?? ""}
            onChange={(e) => set("date_to", e.target.value)}
          />
        </div>
        <label className="flex h-9 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={withReads}
            onChange={(e) => set("reads", e.target.checked ? "1" : "")}
          />
          Include views and downloads
        </label>
        {filtered && (
          <Button variant="ghost" onClick={() => setParams({}, { replace: true })}>
            Clear filters
          </Button>
        )}
      </div>
      {events.isError ? (
        <EmptyState
          icon={ShieldAlert}
          title="We couldn't load the audit log"
          description="Check your connection and try again."
          action={<Button onClick={() => void events.refetch()}>Try again</Button>}
        />
      ) : (
        <div className="grid gap-4">
          <DataTable
            columns={columns}
            rows={rows}
            getRowKey={(e) => e.id}
            loading={!lab || events.isLoading}
            onRowClick={setOpen}
            empty={
              <EmptyState
                icon={ScrollText}
                title={filtered ? "No matching activity" : "No activity yet"}
                description={
                  filtered
                    ? "Try widening the filters."
                    : "The audit log records sign-ins, membership and role changes, invitations, project changes, document views and downloads, exports and deletions."
                }
              />
            }
          />
          {events.hasNextPage && (
            <Button
              variant="outline"
              className="justify-self-center"
              disabled={events.isFetchingNextPage}
              onClick={() => void events.fetchNextPage()}
            >
              Load more
            </Button>
          )}
        </div>
      )}
      <DetailPanel
        open={!!open}
        onOpenChange={(o) => !o && setOpen(null)}
        title={open ? actionText(open) : "Event"}
        description={open ? who(open) : undefined}
      >
        {open && <EventDetails e={open} />}
      </DetailPanel>
    </>
  );
}

const ROLE_WORDS: Record<string, string> = {
  pi: "PI",
  lab_admin: "Lab admin",
  member: "Member",
  viewer: "Viewer",
};

/** Hide raw ids that older backend labels embed (e.g. "<uuid> is viewer"). */
const cleanTarget = (label?: string | null) =>
  label
    ? label
        .replace(
          /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12} is (pi|lab_admin|member|viewer)\b/g,
          (_, role: string) => `A lab member (${ROLE_WORDS[role]})`,
        )
        .replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/g, "a lab member")
    : "—";
