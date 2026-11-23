import { ListChecks } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router";
import { DueChip } from "@/components/dashboard/DueChip";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { PageHeader } from "@/components/shared/PageHeader";
import { useTeamTasks } from "@/hooks/projects";
import { useLab, useMembers } from "@/hooks/workspace";
import { personName, taskStatusLabel, type MyTask } from "@/lib/api-types";
import { shortDate } from "@/lib/dashboard";
import { formErrors } from "@/lib/forms";

const KINDS: Record<string, string> = {
  overdue: "overdue tasks",
  in_progress: "tasks in progress",
  open: "open tasks",
};

/** One member's tasks behind a count on Home's Team table. PIs and lab admins only (server-side). */
export function TeamTasksPage() {
  const { labId = "" } = useParams();
  const [params] = useSearchParams();
  const assignee = params.get("assignee") ?? "";
  const show = params.get("show") && KINDS[params.get("show")!] ? params.get("show")! : "open";
  const allowed = useLab(labId).data?.my_permissions.includes("manage_lab") ?? false;
  const person = useMembers(labId).data?.find((m) => m.user.id === assignee)?.user;
  const { data, isLoading, error } = useTeamTasks(labId, allowed ? assignee : "", show);

  const columns: Column<MyTask>[] = [
    {
      key: "title",
      header: "Task",
      cell: (t) => (
        <Link
          to={`/labs/${labId}/projects/${t.project}/tasks?task=${t.id}`}
          className="font-medium underline-offset-2 hover:underline"
        >
          {t.title}
        </Link>
      ),
    },
    { key: "project", header: "Project", cell: (t) => t.project_name },
    { key: "status", header: "Status", cell: (t) => taskStatusLabel(t.status) },
    {
      key: "due",
      header: "Due",
      cell: (t) =>
        t.due_date ? (
          <span className="flex flex-wrap items-center gap-2">
            {shortDate(t.due_date)}
            <DueChip due={t.due_date} status={t.status} />
          </span>
        ) : (
          <span className="text-muted-foreground">No date</span>
        ),
    },
  ];
  if (error) return <FormError message={formErrors(error, []).form} />;
  return (
    <>
      <PageHeader
        title={person ? `${personName(person)}: ${KINDS[show]}` : `Team: ${KINDS[show]}`}
        description="Across every project you can see."
        actions={
          <Link
            to={`/labs/${labId}/dashboard`}
            className="text-sm underline-offset-2 hover:underline"
          >
            Back to Home
          </Link>
        }
      />
      <DataTable
        columns={columns}
        rows={data ?? []}
        getRowKey={(t) => t.id}
        loading={isLoading}
        empty={
          <EmptyState
            icon={ListChecks}
            title="Nothing here"
            description={`No ${KINDS[show]} for this person right now.`}
          />
        }
      />
    </>
  );
}
