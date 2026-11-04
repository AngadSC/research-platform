import { ScrollText, ShieldAlert } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useParams, useSearchParams } from "react-router";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { DetailPanel } from "@/components/shared/DetailPanel";
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
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAuditEvents, useLab, useMembers, type AuditFilters } from "@/hooks/workspace";
import { ApiError } from "@/lib/api";
import type { AuditEvent } from "@/lib/api-types";

const ACTIONS: Record<string, string> = {
  "auth.login": "Signed in",
  "auth.login_failed": "Failed sign-in attempt",
  "auth.logout": "Signed out",
  "auth.password_changed": "Changed a password",
  "auth.mfa_enabled": "Turned on two-step verification",
  "auth.mfa_disabled": "Turned off two-step verification",
  "lab.created": "Created the lab",
  "lab.updated": "Updated the lab",
  "membership.invited": "Invited a member",
  "membership.invite_revoked": "Revoked an invitation",
  "membership.invite_accepted": "Accepted an invitation",
  "membership.role_changed": "Changed a member's role",
  "membership.removed": "Removed a member",
  "project_membership.added": "Added someone to a project",
  "project_membership.role_changed": "Changed a project role",
  "project_membership.removed": "Removed someone from a project",
  "project.created": "Created a project",
  "project.updated": "Updated a project",
  "project.deleted": "Deleted a project",
  "project.exported": "Exported a project",
  "document.viewed": "Viewed a document",
  "document.restored": "Restored a document",
  "document.deleted": "Deleted a document",
  "attachment.uploaded": "Uploaded a file",
  "attachment.downloaded": "Downloaded a file",
  "attachment.deleted": "Deleted a file",
  "task.deleted": "Deleted a task",
  "deadline.deleted": "Deleted a deadline",
  "dataset.deleted": "Deleted a dataset",
  "analysis.deleted": "Deleted an analysis",
  "result.deleted": "Deleted a result",
  "decision.deleted": "Deleted a decision",
  "manuscript.deleted": "Deleted a manuscript",
  "ethics_approval.deleted": "Deleted an ethics approval",
  "audit_log.viewed": "Viewed the audit log",
  "handover.generated": "Generated a handover",
};
const actionLabel = (a: string) => ACTIONS[a] ?? a;
const who = (e: AuditEvent) => e.actor?.display_name || e.actor?.email || "System";
const exact = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" });

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 31536000],
  ["month", 2592000],
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
];
function relative(iso: string) {
  const secs = (new Date(iso).getTime() - Date.now()) / 1000;
  const [unit, size] = UNITS.find(([, s]) => Math.abs(secs) >= s) ?? ["second", 1];
  return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(
    Math.round(secs / size),
    unit,
  );
}

const show = (v: unknown) => (typeof v === "string" ? v : JSON.stringify(v));
const humanKey = (k: string) => k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

function EventDetails({ e }: { e: AuditEvent }) {
  const meta = e.metadata && typeof e.metadata === "object" ? Object.entries(e.metadata) : [];
  return (
    <dl className="grid gap-4 py-4">
      <Field label="When">{exact(e.created_at)}</Field>
      <Field label="Who">{who(e)}</Field>
      <Field label="Action">
        {actionLabel(e.action)} <span className="text-xs text-muted-foreground">({e.action})</span>
      </Field>
      <Field label="Target">{cleanTarget(e.target_label)}</Field>
      {e.target_type && <Field label="Target type">{e.target_type}</Field>}
      <Field label="IP address">{e.ip ?? "—"}</Field>
      {meta.length > 0 && (
        <Field label="Details">
          <dl className="grid gap-2 rounded-md border p-3">
            {meta.map(([k, v]) => (
              <Field key={k} label={humanKey(k)}>
                {show(v)}
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
    cell: (e) => (
      <Tooltip>
        <TooltipTrigger asChild>
          <time dateTime={e.created_at}>{relative(e.created_at)}</time>
        </TooltipTrigger>
        <TooltipContent>{exact(e.created_at)}</TooltipContent>
      </Tooltip>
    ),
  },
  { key: "who", header: "Who", cell: who },
  { key: "action", header: "Action", cell: (e) => actionLabel(e.action) },
  { key: "target", header: "Target", cell: (e) => cleanTarget(e.target_label) },
  { key: "ip", header: "IP address", cell: (e) => e.ip ?? "—" },
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
  const events = useAuditEvents(labId, filters, !!allowed);
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
        title={open ? actionLabel(open.action) : "Event"}
        description={open ? who(open) : undefined}
      >
        {open && <EventDetails e={open} />}
      </DetailPanel>
    </>
  );
}

/** Hide raw ids that backend labels sometimes embed (e.g. "<uuid> is member"). */
const cleanTarget = (label?: string | null) =>
  label
    ? label.replace(
        /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}( is member)?/g,
        "a lab member",
      )
    : "�";
