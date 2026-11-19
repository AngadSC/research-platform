import { ParticipantCards } from "@/components/dashboard/ParticipantCards";
import { CalendarClock, CircleAlert, GraduationCap } from "lucide-react";
import { Link, useParams } from "react-router";
import { StatusPill } from "@/components/training/ComplianceMatrix";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCalendar } from "@/hooks/admin";
import { useMyTasks } from "@/hooks/projects";
import { useMyTraining } from "@/hooks/training";
import { shortDate } from "@/lib/dashboard";
import { dayText } from "@/lib/ethics";
import { localDateISO } from "@/lib/format";
import { isSnoozed } from "@/lib/snooze";
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
  const rows = (list.data ?? [])
    .filter((i) => i.kind === "deadline" && !i.done)
    .sort((a, b) => a.date.localeCompare(b.date)); // overdue ones are the oldest, so they lead
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
          className={
            d.date < today
              ? "flex flex-wrap items-center justify-between gap-3 rounded-md border border-danger/50 bg-danger/5 p-3"
              : "flex flex-wrap items-center justify-between gap-3 rounded-md border p-3"
          }
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
              {(cell.expires_on || cell.record) && (
                <p className="text-xs text-muted-foreground">
                  {cell.expires_on
                    ? `${cell.status === "expired" ? "Expired" : "Expires"} ${dayText(cell.expires_on)}`
                    : "Doesn't expire"}
                </p>
              )}
            </div>
            <div className="flex items-center gap-2">
              <StatusPill status={cell.status} />
              {cell.status !== "done" && (
                <Button variant="outline" size="sm" asChild>
                  <Link
                    to={`/labs/${labId}/training?log=${r.id}`}
                    aria-label={`Log completion of ${r.name}`}
                  >
                    Log completion
                  </Link>
                </Button>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/** Everything of yours that is already late, first on the page. Nothing renders when all is on time. */
function OverdueNow({ labId }: { labId: string }) {
  const today = localDateISO();
  const tasks = (useMyTasks(labId).data ?? []).filter(
    (t) => t.due_date && t.due_date < today && !isSnoozed(t.snoozed_until),
  );
  const { list } = useCalendar(labId, addDays(-30), addDays(0), true);
  const deadlines = (list.data ?? []).filter(
    (i) => i.kind === "deadline" && !i.done && i.date < today,
  );
  if (tasks.length + deadlines.length === 0) return null;
  return (
    <section aria-labelledby="overdue-now" className="rounded-xl border bg-card p-4">
      <h2 id="overdue-now" className="flex items-center gap-2 text-base font-medium">
        <CircleAlert className="size-4 text-danger-text" aria-hidden />
        Overdue · {tasks.length + deadlines.length}
      </h2>
      <ul className="mt-2 grid gap-1 text-sm">
        {deadlines.map((d) => (
          <li key={`d-${d.id}`}>
            <Link
              to={`/labs/${labId}/projects/${d.project_id}/overview`}
              className="font-medium underline-offset-2 hover:underline"
            >
              {d.title}
            </Link>{" "}
            <span className="text-muted-foreground">
              · deadline · {d.project_name} · due {shortDate(d.date)}
            </span>
          </li>
        ))}
        {tasks.map((t) => (
          <li key={`t-${t.id}`}>
            <Link
              to={`/labs/${labId}/projects/${t.project}/tasks?task=${t.id}`}
              className="font-medium underline-offset-2 hover:underline"
            >
              {t.title}
            </Link>{" "}
            <span className="text-muted-foreground">
              · task · {t.project_name} · due {shortDate(t.due_date!)}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** One person's own view of what they have to do, across every project in this lab. */
export function MyWorkPage() {
  const { labId = "" } = useParams();
  return (
    <>
      <PageHeader title="My work" description="Your tasks, deadlines and trainings in this lab." />
      <div className="grid gap-4">
        <OverdueNow labId={labId} />
        <ParticipantCards labId={labId} compact />
        <Section
          title="Tasks"
          description="Open tasks assigned to you, soonest due first."
          defaultOpen
        >
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
