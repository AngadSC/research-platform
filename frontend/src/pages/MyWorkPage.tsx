import { CalendarClock, GraduationCap } from "lucide-react";
import { Link, useParams } from "react-router";
import { StatusPill } from "@/components/training/ComplianceMatrix";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { PageHeader } from "@/components/shared/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { useCalendar } from "@/hooks/admin";
import { useMyTraining } from "@/hooks/training";
import { shortDate } from "@/lib/dashboard";
import { dayText } from "@/lib/ethics";
import { localDateISO } from "@/lib/format";
import { formErrors } from "@/lib/forms";
import { Section } from "@/pages/admin/common";
import { MyTasksList } from "@/pages/MyTasksPage";

const addDays = (days: number) => {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return localDateISO(d);
};

function MyDeadlines({ labId }: { labId: string }) {
  // The calendar API allows 92 days at a time: a month back and two months ahead.
  const { list } = useCalendar(labId, addDays(-30), addDays(61), true);
  const today = localDateISO();
  if (list.error) return <FormError message={formErrors(list.error, []).form} />;
  if (list.isLoading) return <Skeleton className="h-24 w-full" />;
  const rows = (list.data ?? []).filter((i) => i.kind === "deadline" && !i.done);
  if (rows.length === 0)
    return (
      <EmptyState
        icon={CalendarClock}
        title="No deadlines coming up"
        description="Deadlines in the projects you are on will show up here."
      />
    );
  return (
    <ul className="grid gap-2" aria-label="My deadlines">
      {rows.map((d) => (
        <li
          key={d.id}
          className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3"
        >
          <div className="min-w-0">
            <Link
              to={`/labs/${labId}/projects/${d.project_id}/overview`}
              className="font-medium underline-offset-2 hover:underline"
            >
              {d.title}
            </Link>
            <p className="text-xs text-muted-foreground">{d.project_name}</p>
          </div>
          {d.date < today ? (
            <span className="text-sm font-medium text-danger-text">
              {shortDate(d.date)} (overdue)
            </span>
          ) : (
            <span className="text-sm">{shortDate(d.date)}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

function MyTrainings({ labId }: { labId: string }) {
  const { data, error, isLoading } = useMyTraining(labId);
  if (error) return <FormError message={formErrors(error, []).form} />;
  if (isLoading) return <Skeleton className="h-24 w-full" />;
  const row = data?.members[0];
  const required = data?.requirements.filter((r) => row?.cells[r.id]) ?? [];
  if (required.length === 0)
    return (
      <EmptyState
        icon={GraduationCap}
        title="No trainings required of you"
        description="When the lab adds a required training that applies to you, it will show here."
      />
    );
  return (
    <ul className="grid gap-2" aria-label="My trainings">
      {required.map((r) => {
        const cell = row!.cells[r.id]!;
        return (
          <li
            key={r.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3"
          >
            <div className="min-w-0">
              <Link
                to={`/labs/${labId}/training`}
                className="font-medium underline-offset-2 hover:underline"
              >
                {r.name}
              </Link>
              {cell.expires_on && (
                <p className="text-xs text-muted-foreground">
                  {cell.status === "expired" ? "Expired" : "Expires"} {dayText(cell.expires_on)}
                </p>
              )}
            </div>
            <StatusPill status={cell.status} />
          </li>
        );
      })}
    </ul>
  );
}

/** One person's own view of what they have to do, across every project in this lab. */
export function MyWorkPage() {
  const { labId = "" } = useParams();
  return (
    <>
      <PageHeader title="My work" description="Your tasks, deadlines and trainings in this lab." />
      <div className="grid gap-8">
        <Section title="Tasks" description="Open tasks assigned to you, soonest due first.">
          <MyTasksList labId={labId} />
        </Section>
        <Section
          title="Deadlines"
          description="In the projects you are on: the next two months, and any missed in the last month."
        >
          <MyDeadlines labId={labId} />
        </Section>
        <Section title="Trainings" description="What the lab requires of you, and where you stand.">
          <MyTrainings labId={labId} />
        </Section>
      </div>
    </>
  );
}
