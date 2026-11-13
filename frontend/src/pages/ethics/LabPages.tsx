import { Archive, Bell } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useMarkRead, useNotifications, useRetentionDue } from "@/hooks/ethics";
import { useLab } from "@/hooks/workspace";
import type { AppNotification, RetentionItem } from "@/lib/api-types";
import { dayText } from "@/lib/ethics";
import { when } from "@/lib/format";

export function NotificationsPage() {
  const { labId = "" } = useParams();
  const navigate = useNavigate();
  const { data, isLoading } = useNotifications(labId);
  const { one, all } = useMarkRead(labId);
  const hasUnread = (data ?? []).some((n) => !n.read_at);
  const cols: Column<AppNotification>[] = [
    {
      key: "t",
      header: "Notification",
      cell: (n) => (
        <div className="grid">
          <Link
            to={n.url}
            className={n.read_at ? "hover:underline" : "font-medium hover:underline"}
            onClick={() => !n.read_at && one.mutate(n.id)}
          >
            {n.title}
          </Link>
          {n.body && <span className="text-xs text-muted-foreground">{n.body}</span>}
        </div>
      ),
    },
    { key: "d", header: "When", cell: (n) => when(n.created_at) },
    {
      key: "a",
      header: "Actions",
      className: "text-right",
      cell: (n) =>
        n.read_at ? (
          <span className="text-xs text-muted-foreground">Read</span>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            aria-label={`Mark as read: ${n.title}`}
            onClick={() => one.mutate(n.id)}
          >
            Mark as read
          </Button>
        ),
    },
  ];
  return (
    <div>
      <PageHeader
        title="Notifications"
        description="Reminders and updates for this lab."
        actions={
          <Button
            variant="outline"
            disabled={!hasUnread || all.isPending}
            onClick={() => all.mutate()}
          >
            Mark all as read
          </Button>
        }
      />
      <DataTable
        columns={cols}
        rows={data ?? []}
        getRowKey={(n) => n.id}
        loading={isLoading}
        empty={
          <EmptyState
            icon={Bell}
            title="You are all caught up"
            description="Reminders about expiring ethics approvals and retention reviews will show up here."
            action={
              <Button variant="outline" onClick={() => void navigate(`/labs/${labId}`)}>
                Back to the lab
              </Button>
            }
          />
        }
      />
    </div>
  );
}

export const RETENTION_BANNER =
  "Nothing is deleted automatically. Review each item and decide what to keep.";

export function RetentionPage() {
  const { labId = "" } = useParams();
  const { data: lab } = useLab(labId);
  const allowed = lab?.my_permissions.includes("view_retention") ?? false;
  const { data, isLoading } = useRetentionDue(labId, allowed);
  if (lab && !allowed)
    return (
      <EmptyState
        icon={Archive}
        title="Retention review is for PIs and lab admins"
        description="You don't have access to this page."
      />
    );
  const link = (r: RetentionItem) =>
    r.kind === "project"
      ? `/labs/${labId}/projects/${r.project_id}`
      : `/labs/${labId}/projects/${r.project_id}/documents/${r.id}`;
  const cols: Column<RetentionItem>[] = [
    {
      key: "n",
      header: "Item",
      cell: (r) => (
        <div className="grid">
          <Link to={link(r)} className="font-medium hover:underline">
            {r.name}
          </Link>
          {r.kind === "document" && (
            <span className="text-xs text-muted-foreground">In {r.project_name}</span>
          )}
        </div>
      ),
    },
    { key: "k", header: "Type", cell: (r) => (r.kind === "project" ? "Project" : "Document") },
    { key: "d", header: "Keep until", cell: (r) => dayText(r.retain_until) },
    { key: "note", header: "Note", cell: (r) => r.retention_note || "None" },
    {
      key: "s",
      header: "Status",
      cell: (r) =>
        r.deleted_at ? <Badge variant="destructive">Deleted</Badge> : <Badge>Past its date</Badge>,
    },
  ];
  return (
    <div className="grid gap-4">
      <PageHeader
        title="Retention review"
        description="Projects and documents past their keep-until date."
      />
      <p
        role="note"
        className="rounded-md border border-primary/40 bg-primary/10 p-3 text-sm font-medium"
      >
        {RETENTION_BANNER}
      </p>
      <DataTable
        columns={cols}
        rows={data ?? []}
        getRowKey={(r) => `${r.kind}-${r.id}`}
        loading={isLoading || !lab}
        empty={
          <EmptyState
            icon={Archive}
            title="Nothing to review"
            description="No project or document is past its keep-until date."
          />
        }
      />
    </div>
  );
}
