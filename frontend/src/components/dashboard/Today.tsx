import { ArrowRight, Check, Clock, PartyPopper } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useDelight, useRecents } from "@/hooks/preferences";
import { useMyTasks, usePatchTask } from "@/hooks/projects";
import type { MyTask } from "@/lib/api-types";
import { shortDate } from "@/lib/dashboard";
import { localDateISO } from "@/lib/format";
import { addDays, nextMonday } from "@/lib/snooze";
import { projectColorStyle } from "@/lib/projectColors";
import { cn } from "@/lib/utils";

function Row({ labId, task, today }: { labId: string; task: MyTask; today: string }) {
  const patch = usePatchTask(labId);
  const delight = useDelight();
  const [leaving, setLeaving] = useState(false);
  const late = !!task.due_date && task.due_date < today;
  const monday = nextMonday(today);

  const done = () => {
    setLeaving(true);
    patch.mutate(
      { id: task.id, patch: { status: "done" } },
      {
        onError: () => {
          setLeaving(false);
          toast.error("Could not mark that done. Try again.");
        },
      },
    );
  };
  const snooze = (until: string, label: string) =>
    patch.mutate(
      { id: task.id, patch: { snoozed_until: until } },
      {
        onSuccess: () =>
          toast(`Snoozed until ${label}`, {
            action: {
              label: "Undo",
              onClick: () => patch.mutate({ id: task.id, patch: { snoozed_until: null } }),
            },
          }),
        onError: () => toast.error("Could not snooze that."),
      },
    );

  return (
    <li
      style={projectColorStyle(task.project_color)}
      className={cn(
        "flex items-center gap-3 border-b px-3 py-2 last:border-b-0",
        leaving && (delight ? "delight-out" : "hidden"),
      )}
    >
      <button
        type="button"
        aria-label={`Mark "${task.title}" done`}
        onClick={done}
        disabled={leaving}
        className={cn(
          "grid size-6 shrink-0 place-items-center rounded-full border-2 border-(--project) text-primary-foreground hover:bg-(--project)/20 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
          leaving && "bg-(--project)",
          leaving && delight && "delight-pop",
        )}
      >
        {leaving && <Check className="size-3.5" strokeWidth={3} aria-hidden />}
      </button>
      <Link
        to={`/labs/${labId}/projects/${task.project}/tasks?task=${task.id}`}
        className="min-w-0 flex-1 text-sm font-medium break-words hover:underline"
      >
        {task.title}
        <span className="block text-xs font-normal text-muted-foreground">
          {task.project_name}
          {task.due_date && ` · ${late ? "was due" : "due"} ${shortDate(task.due_date)}`}
        </span>
      </Link>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm" aria-label={`Snooze "${task.title}"`}>
            <Clock aria-hidden /> <span className="hidden sm:inline">Snooze</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={() => snooze(addDays(today, 1), "tomorrow")}>
            Until tomorrow
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => snooze(monday, "Monday")}>
            Until Monday
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </li>
  );
}

function Group({
  title,
  tone,
  labId,
  tasks,
  today,
}: {
  title: string;
  tone?: "late";
  labId: string;
  tasks: MyTask[];
  today: string;
}) {
  if (tasks.length === 0) return null;
  return (
    <section aria-label={title} className="grid gap-1">
      <h3
        className={cn(
          "text-xs font-semibold tracking-wider uppercase",
          tone === "late" ? "text-danger-text" : "text-muted-foreground",
        )}
      >
        {title} · {tasks.length}
      </h3>
      <ul className="overflow-hidden rounded-lg border">
        {tasks.map((t) => (
          <Row key={t.id} labId={labId} task={t} today={today} />
        ))}
      </ul>
    </section>
  );
}

/** Home for students: what is overdue, what is due today, and one button back to what you were
 * last working on. Snoozed tasks wait out of sight until their day. */
export function Today({ labId }: { labId: string }) {
  const { data: tasks, isLoading } = useMyTasks(labId);
  const recents = useRecents();
  const delight = useDelight();
  const today = localDateISO();
  const open = (tasks ?? []).filter((t) => !t.snoozed_until || t.snoozed_until <= today);
  const overdue = open.filter((t) => t.due_date && t.due_date < today);
  const dueToday = open.filter((t) => t.due_date === today);
  const snoozed = (tasks ?? []).length - open.length;
  // What you were last editing: the latest document or record, else the latest page at all.
  const last = recents.find((r) => r.kind === "document" || r.kind === "record") ?? recents[0];
  const caughtUp = !isLoading && overdue.length === 0 && dueToday.length === 0;

  return (
    <section aria-labelledby="today" className="mb-8 grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="today" className="text-xl font-semibold tracking-tight">
          Today
          <span className="ml-2 text-sm font-normal text-muted-foreground">
            {new Date().toLocaleDateString(undefined, {
              weekday: "long",
              month: "long",
              day: "numeric",
            })}
          </span>
        </h2>
        {last && (
          <Button asChild>
            <Link to={last.url}>
              Continue where you left off <ArrowRight aria-hidden />
            </Link>
          </Button>
        )}
      </div>
      {last && (
        <p className="-mt-2 text-sm text-muted-foreground">
          You were last in <span className="font-medium text-foreground">{last.label}</span>.
        </p>
      )}
      <Group title="Overdue" tone="late" labId={labId} tasks={overdue} today={today} />
      <Group title="Due today" labId={labId} tasks={dueToday} today={today} />
      {caughtUp && (
        <div
          role="status"
          className={cn(
            "flex items-center gap-3 rounded-lg border bg-success/5 p-4",
            delight && "delight-rise",
          )}
        >
          <PartyPopper className="size-6 shrink-0 text-success-text" aria-hidden />
          <div>
            <p className="font-medium">You are all caught up.</p>
            <p className="text-sm text-muted-foreground">
              Nothing is due today and nothing is overdue.
              {snoozed > 0 &&
                ` ${snoozed} snoozed task${snoozed === 1 ? " is" : "s are"} resting.`}{" "}
              Press <kbd>Ctrl</kbd>/<kbd>Cmd</kbd> + G to add something for later.
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
