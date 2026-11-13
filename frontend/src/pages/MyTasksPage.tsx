import { ListChecks } from "lucide-react";
import { Link } from "react-router";
import { DueChip } from "@/components/dashboard/DueChip";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { useMyTasks } from "@/hooks/projects";
import { useLab } from "@/hooks/workspace";
import { taskStatusLabel, type MyTask } from "@/lib/api-types";
import { shortDate } from "@/lib/dashboard";
import { formErrors } from "@/lib/forms";

/** Your open tasks across the lab, soonest due first. On My work, and on Home for members. */
export function MyTasksList({ labId }: { labId: string }) {
  const { data, isLoading, error } = useMyTasks(labId);
  const viewer = useLab(labId).data?.my_role === "viewer";
  const cols: Column<MyTask>[] = [
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
        !t.due_date ? (
          <span className="text-muted-foreground">No date</span>
        ) : (
          <span className="flex flex-wrap items-center gap-2">
            {shortDate(t.due_date)}
            <DueChip due={t.due_date} status={t.status} />
          </span>
        ),
    },
  ];
  if (error) return <FormError message={formErrors(error, []).form} />;
  return (
    <DataTable
      columns={cols}
      rows={data ?? []}
      getRowKey={(t) => t.id}
      loading={isLoading}
      empty={
        <EmptyState
          icon={ListChecks}
          title="Nothing assigned to you"
          description={
            viewer
              ? "Viewers can't be given tasks. Ask a PI or lab admin if you need to take part."
              : "Tasks assigned to you in any project will show up here."
          }
        />
      }
    />
  );
}
