import { ChevronRight, Sun } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useMyTasks } from "@/hooks/projects";
import { useMe } from "@/hooks/workspace";
import type { MyTask } from "@/lib/api-types";
import { shortDate } from "@/lib/dashboard";
import { localDateISO } from "@/lib/format";
import { greeting } from "@/lib/greeting";
import { plural } from "@/lib/format";
import { addDays } from "@/lib/snooze";
import { projectColorStyle } from "@/lib/projectColors";

/** Your tasks sorted for the morning. Snoozed ones are resting until their day. */
export function digestOf(tasks: MyTask[], today: string) {
  const awake = tasks.filter((t) => !t.snoozed_until || t.snoozed_until <= today);
  const week = addDays(today, 7);
  return {
    overdue: awake.filter((t) => t.due_date && t.due_date < today),
    today: awake.filter((t) => t.due_date === today),
    soon: awake.filter((t) => t.due_date && t.due_date > today && t.due_date <= week),
    resting: tasks.length - awake.length,
  };
}

function List({ labId, title, tasks }: { labId: string; title: string; tasks: MyTask[] }) {
  if (tasks.length === 0) return null;
  return (
    <section aria-label={title} className="grid gap-1">
      <h3 className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">
        {title} · {tasks.length}
      </h3>
      <ul className="grid gap-1">
        {tasks.map((t) => (
          <li key={t.id} style={projectColorStyle(t.project_color)}>
            <Link
              to={`/labs/${labId}/projects/${t.project}/tasks?task=${t.id}`}
              className="flex items-start gap-2 rounded-md border-l-4 border-(--project) bg-muted/40 px-3 py-2 text-sm hover:bg-muted"
            >
              <span className="min-w-0 flex-1">
                <span className="block font-medium break-words">{t.title}</span>
                <span className="block text-xs text-muted-foreground">
                  {t.project_name}
                  {t.due_date && ` · ${shortDate(t.due_date)}`}
                </span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** A card on Home that opens the morning digest in the app: what is due, what is overdue and what
 * is coming this week. It is read here, not sent by email. */
export function MorningDigest({ labId }: { labId: string }) {
  const [open, setOpen] = useState(false);
  const name = (useMe().data as { display_name?: string } | undefined)?.display_name ?? "";
  const { data: tasks, isLoading } = useMyTasks(labId);
  const today = localDateISO();
  const d = digestOf(tasks ?? [], today);
  const due = d.today.length + d.overdue.length;
  const summary = isLoading
    ? "Loading"
    : due === 0
      ? "Nothing due today"
      : [
          d.today.length && `${d.today.length} due today`,
          d.overdue.length && `${d.overdue.length} overdue`,
        ]
          .filter(Boolean)
          .join(" · ");

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mb-6 flex w-full items-center gap-3 rounded-lg border bg-card p-4 text-left hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none sm:w-auto sm:min-w-80"
      >
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-warning/20 text-warning-text">
          <Sun className="size-5" aria-hidden />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block font-semibold">Morning digest</span>
          <span className="block text-sm text-muted-foreground">{summary}</span>
        </span>
        <ChevronRight className="size-4 text-muted-foreground" aria-hidden />
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogTitle className="text-lg font-semibold">{greeting(new Date(), name)}</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            {due === 0
              ? "Nothing is due today and nothing is overdue."
              : `${plural(due, "thing")} need${due === 1 ? "s" : ""} you today.`}
          </DialogDescription>
          <div className="grid gap-4">
            <List labId={labId} title="Overdue" tasks={d.overdue} />
            <List labId={labId} title="Due today" tasks={d.today} />
            <List labId={labId} title="Coming up this week" tasks={d.soon} />
            {due + d.soon.length === 0 && (
              <p role="status" className="text-sm">
                You are all caught up. Enjoy it.
              </p>
            )}
            {d.resting > 0 && (
              <p className="text-xs text-muted-foreground">
                {plural(d.resting, "snoozed task")} resting until{" "}
                {d.resting === 1 ? "its" : "their"} day.
              </p>
            )}
            <Link
              to={`/labs/${labId}/my-work`}
              onClick={() => setOpen(false)}
              className="text-sm text-primary hover:underline"
            >
              Open My work
            </Link>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
