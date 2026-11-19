import { ListChecks } from "lucide-react";
import { useIsPhone } from "@/hooks/media";
import { Link } from "react-router";
import { DueChip } from "@/components/dashboard/DueChip";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { useMyTasks, usePatchTask } from "@/hooks/projects";
import { useLab } from "@/hooks/workspace";
import { taskStatusLabel, type MyTask } from "@/lib/api-types";
import { shortDate } from "@/lib/dashboard";
import { formErrors } from "@/lib/forms";
import { Button } from "@/components/ui/button";
import { isSnoozed, snoozeEnds } from "@/lib/snooze";

/** Your open tasks across the lab, soonest due first. On My work, and on Home for members. */
export function MyTasksList({ labId }: { labId: string }) {
  const { data, isLoading, error } = useMyTasks(labId);
  const viewer = useLab(labId).data?.my_role === "viewer";
  const patch = usePatchTask(labId);
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
    {
      key: "status",
      header: "Status",
      cell: (t) =>
        isSnoozed(t.snoozed_until) ? (
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground">
              Snoozed until {snoozeEnds(t.snoozed_until!)}
            </span>
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Unsnooze "${t.title}"`}
              onClick={() => patch.mutate({ id: t.id, patch: { snoozed_until: null } })}
            >
              Unsnooze
            </Button>
          </span>
        ) : (
          taskStatusLabel(t.status)
        ),
    },
    {
      key: "due",
      header: "Due",
      cell: (t) =>
        !t.due_date ? (
          <span className="text-muted-foreground">No date</span>
        ) : (
          <span className="flex flex-wrap items-center gap-2">
            {shortDate(t.due_date)}
            {!isSnoozed(t.snoozed_until) && <DueChip due={t.due_date} status={t.status} />}
          </span>
        ),
    },
  ];
  const phone = useIsPhone();
  if (error) return <FormError message={formErrors(error, []).form} />;
  // On a phone five narrow columns are unreadable: stack each task instead.
  if (phone && data && data.length > 0)
    return (
      <ul className="divide-y rounded-lg border">
        {data.map((t) => (
          <li key={t.id} className="grid gap-1 p-3 text-sm">
            {cols[0]!.cell(t)}
            <span className="text-xs text-muted-foreground">{t.project_name}</span>
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
              {cols[2]!.cell(t)}
              {cols[3]!.cell(t)}
            </span>
          </li>
        ))}
      </ul>
    );
  return (
    <DataTable
      columns={cols}
      rows={data ?? []}
      getRowKey={(t) => t.id}
      loading={isLoading}
      empty={
        <EmptyState
          icon={ListChecks}
          title="You are all caught up"
          description={
            viewer
              ? "Viewers can't be given tasks. Ask a PI or lab admin if you need to take part."
              : "Nothing is assigned to you right now. Tasks given to you in any project will show up here."
          }
        />
      }
    />
  );
}
