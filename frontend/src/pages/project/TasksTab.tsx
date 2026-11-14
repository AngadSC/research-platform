import { LayoutList, ListChecks, MoreHorizontal, Plus, SquareKanban } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { DueChip } from "@/components/dashboard/DueChip";
import { DataTable, HIDE_NARROW, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useProviders } from "@/hooks/integrations";
import { useDelight } from "@/hooks/preferences";
import { useProjectMembers, useTaskView, useTasks } from "@/hooks/projects";
import {
  TASK_STATUSES,
  personName,
  taskStatusLabel,
  type Task,
  type TaskStatus,
} from "@/lib/api-types";
import { plural } from "@/lib/format";
import { projectColorStyle } from "@/lib/projectColors";
import { cn } from "@/lib/utils";
import { TASK_TONES } from "@/lib/taskColors";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { ImportTasksDialog } from "@/pages/project/ImportTasksDialog";
import { NewTaskPanel } from "@/pages/project/NewTaskPanel";
import { TaskDrawer } from "@/pages/project/TaskDrawer";

const day = (iso: string | null) =>
  iso ? new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { dateStyle: "medium" }) : "";
const NONE = "none";

type MoveFn = (task: Task, status: TaskStatus, index: number) => void;

function MoveMenu({ task, tasks, move }: { task: Task; tasks: Task[]; move: MoveFn }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" aria-label={`Move ${task.title}`}>
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {TASK_STATUSES.filter((s) => s.value !== task.status).map((s) => (
          <DropdownMenuItem
            key={s.value}
            onSelect={() => move(task, s.value, tasks.filter((t) => t.status === s.value).length)}
          >
            Move to {s.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Status chip in the status colours (D144). */
function ToneChip({ status }: { status: TaskStatus }) {
  const t = TASK_TONES[status];
  return (
    <span
      className="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold whitespace-nowrap"
      style={{ backgroundColor: t.strong, color: t.onStrong }}
    >
      {taskStatusLabel(status)}
    </span>
  );
}

function Board({
  tasks,
  canEdit,
  move,
  onOpen,
  color,
}: {
  color: string;
  tasks: Task[];
  canEdit: boolean;
  move: MoveFn;
  onOpen: (t: Task) => void;
}) {
  const [dragId, setDragId] = useState<string | null>(null);
  // A small pop on a card that has just been finished, when animations are on.
  const delight = useDelight();
  const seen = useRef(new Map<string, string>());
  const [popped, setPopped] = useState<string[]>([]);
  useEffect(() => {
    const finished = tasks
      .filter(
        (t) => t.status === "done" && seen.current.has(t.id) && seen.current.get(t.id) !== "done",
      )
      .map((t) => t.id);
    seen.current = new Map(tasks.map((t) => [t.id, t.status]));
    if (!finished.length || !delight) return;
    setPopped(finished);
    const id = setTimeout(() => setPopped([]), 700);
    return () => clearTimeout(id);
  }, [tasks, delight]);
  const dropAt = (status: TaskStatus, before?: Task) => {
    const dragged = tasks.find((t) => t.id === dragId);
    setDragId(null);
    if (!dragged) return;
    const col = tasks.filter((t) => t.status === status && t.id !== dragged.id);
    const at = before ? col.findIndex((t) => t.id === before.id) : col.length;
    move(dragged, status, at < 0 ? col.length : at);
  };
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {TASK_STATUSES.map((s) => {
        const col = tasks.filter((t) => t.status === s.value);
        return (
          <section
            key={s.value}
            aria-label={s.label}
            onDragOver={canEdit ? (e) => e.preventDefault() : undefined}
            onDrop={canEdit ? () => dropAt(s.value) : undefined}
            data-status={s.value}
            style={{
              backgroundColor: TASK_TONES[s.value].column,
              color: TASK_TONES[s.value].text,
              borderColor: TASK_TONES[s.value].strong,
            }}
            className="flex min-h-40 flex-col gap-2 rounded-lg border-2 p-3"
          >
            <h2
              className="flex items-center justify-between rounded-md px-2 py-1 text-sm font-semibold"
              style={{
                backgroundColor: TASK_TONES[s.value].strong,
                color: TASK_TONES[s.value].onStrong,
              }}
            >
              <span>{s.label}</span>{" "}
              <span aria-label={plural(col.length, "task")}>{col.length}</span>
            </h2>
            {col.map((t) => (
              <article
                key={t.id}
                draggable={canEdit}
                onDragStart={() => setDragId(t.id)}
                onDrop={
                  canEdit
                    ? (e) => {
                        e.stopPropagation();
                        dropAt(s.value, t);
                      }
                    : undefined
                }
                data-status={t.status}
                style={{
                  backgroundColor: TASK_TONES[t.status].card,
                  color: TASK_TONES[t.status].text,
                  borderLeft: `6px solid ${TASK_TONES[t.status].strong}`,
                  ...projectColorStyle(color),
                  // The project's colour along the top, so a card says which project it is.
                  boxShadow: "inset 0 3px 0 var(--project)",
                }}
                className={cn(
                  "flex items-start justify-between gap-2 rounded-md border border-black/10 p-3",
                  popped.includes(t.id) && "delight-pop",
                )}
              >
                <div className="min-w-0">
                  <button
                    type="button"
                    onClick={() => onOpen(t)}
                    className="text-left text-sm font-medium hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                  >
                    {t.title}
                  </button>
                  <p className="text-xs" style={{ color: TASK_TONES[t.status].muted }}>
                    {[
                      t.assignee && personName(t.assignee),
                      day(t.due_date),
                      t.post_count > 0 && plural(t.post_count, "update"),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                  <DueChip due={t.due_date} status={t.status} />
                </div>
                {canEdit && <MoveMenu task={t} tasks={tasks} move={move} />}
              </article>
            ))}
          </section>
        );
      })}
    </div>
  );
}

// Props: { labId, projectId, project } (ProjectTabProps).
export default function TasksTab({ labId, projectId, project }: ProjectTabProps) {
  const { list, update, remove, move } = useTasks(labId, projectId);
  const members = useProjectMembers(labId, projectId).list.data ?? [];
  const [params, setParams] = useSearchParams();
  const [fStatus, setFStatus] = useState("all");
  const [fAssignee, setFAssignee] = useState("all");
  const canEdit = project.my_permissions.includes("edit_content");
  const [importing, setImporting] = useState(false);
  const pref = useTaskView();
  const asked = params.get("view");
  const view = asked === "list" || asked === "board" ? asked : pref.saved; // D143
  const creating = params.get("new") === "task";
  const openId = params.get("task");
  const isLead = project.my_permissions.includes("edit_project");
  const setParam = (k: string, v: string | null) =>
    setParams(
      (p) => {
        const n = new URLSearchParams(p);
        if (v === null) n.delete(k);
        else n.set(k, v);
        return n;
      },
      { replace: true },
    );

  const setView = (v: "board" | "list") => {
    setParam("view", null); // the account setting is the source of truth, so no URL override
    if (v !== pref.saved) pref.save(v);
  };
  const all = [...(list.data ?? [])].sort((a, b) => a.position - b.position);
  const visible = all.filter(
    (t) =>
      (fStatus === "all" || t.status === fStatus) &&
      (fAssignee === "all" || (fAssignee === NONE ? !t.assignee : t.assignee?.id === fAssignee)),
  );
  const listRows = TASK_STATUSES.flatMap((s) => visible.filter((t) => t.status === s.value));

  const doMove: MoveFn = (task, status, index) =>
    move.mutate(
      { id: task.id, status, position: index },
      {
        onSuccess: () => toast.success(`Moved to ${taskStatusLabel(status)}`),
        onError: () => toast.error("Couldn't move the task, so it was put back. Try again."),
      },
    );

  const cols: Column<Task>[] = [
    { key: "title", header: "Task", cell: (t) => <span className="font-medium">{t.title}</span> },
    { key: "status", header: "Status", cell: (t) => <ToneChip status={t.status} /> },
    {
      key: "assignee",
      header: "Assignee",
      className: HIDE_NARROW,
      cell: (t) => (t.assignee ? personName(t.assignee) : "Unassigned"),
    },
    {
      key: "due",
      header: "Due",
      cell: (t) => (
        <span className="flex flex-wrap items-center gap-2">
          {day(t.due_date) || "No date"}
          <DueChip due={t.due_date} status={t.status} />
        </span>
      ),
    },
    ...(canEdit
      ? [
          {
            key: "actions",
            header: "Actions",
            className: "text-right",
            cell: (t: Task) => <MoveMenu task={t} tasks={all} move={doMove} />,
          },
        ]
      : []),
  ];

  const archived = project.status === "archived"; // no new tasks
  const newTask =
    canEdit && !archived ? (
      <Button onClick={() => setParam("new", "task")}>
        <Plus aria-hidden /> New task
      </Button>
    ) : undefined;
  // Your own connected task apps (D240); nothing shows unless one is connected.
  const taskApps = (useProviders(labId).data ?? []).filter(
    (p) => p.task_import && p.account?.status === "active",
  );
  const empty = (
    <EmptyState
      icon={ListChecks}
      title="A clean slate"
      description={
        archived
          ? "This project is archived. Set it back to Active to add tasks."
          : canEdit
            ? "Nothing to do here yet. Add the first task, or press Ctrl/Cmd + G to jot one down from anywhere."
            : "Only editors can add tasks. Ask the project lead."
      }
      action={newTask}
    />
  );
  const closePanel = () =>
    setParams((p) => {
      for (const k of ["new", "document", "title"]) p.delete(k);
      return p;
    });
  const editing = openId ? all.find((t) => t.id === openId) : undefined;
  const assignable = members
    .filter((m) => m.role !== "viewer")
    .map((m) => ({ id: m.user.id, name: personName(m.user) }));

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="View" className="flex gap-1">
          <Button
            variant={view === "list" ? "secondary" : "ghost"}
            size="sm"
            aria-pressed={view === "list"}
            onClick={() => setView("list")}
          >
            <LayoutList aria-hidden /> List
          </Button>
          <Button
            variant={view === "board" ? "secondary" : "ghost"}
            size="sm"
            aria-pressed={view === "board"}
            onClick={() => setView("board")}
          >
            <SquareKanban aria-hidden /> Board
          </Button>
        </div>
        <div className="flex flex-wrap gap-2">
          {canEdit && !archived && taskApps.length > 0 && (
            <Button variant="outline" onClick={() => setImporting(true)}>
              Import tasks
            </Button>
          )}
          {all.length > 0 && newTask}
        </div>
      </div>
      {view === "list" && all.length > 0 && (
        <div className="flex flex-wrap gap-3">
          <Select value={fStatus} onValueChange={setFStatus}>
            <SelectTrigger aria-label="Filter by status" className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              {TASK_STATUSES.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={fAssignee} onValueChange={setFAssignee}>
            <SelectTrigger aria-label="Filter by assignee" className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Everyone</SelectItem>
              <SelectItem value={NONE}>Unassigned</SelectItem>
              {members.map((m) => (
                <SelectItem key={m.user.id} value={m.user.id}>
                  {personName(m.user)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
      {view === "list" ? (
        <DataTable
          columns={cols}
          rows={listRows}
          getRowKey={(t) => t.id}
          loading={list.isLoading}
          onRowClick={(t) => setParam("task", t.id)}
          empty={
            all.length ? (
              <EmptyState
                title="No matching tasks"
                description="Try a different status or assignee."
              />
            ) : (
              empty
            )
          }
        />
      ) : list.isLoading ? (
        <p aria-busy="true" className="text-sm text-muted-foreground">
          Loading tasks
        </p>
      ) : all.length === 0 ? (
        empty
      ) : (
        <Board
          color={project.color}
          tasks={all}
          canEdit={canEdit}
          move={doMove}
          onOpen={(t) => setParam("task", t.id)}
        />
      )}
      {importing && (
        <ImportTasksDialog
          labId={labId}
          projectId={projectId}
          services={taskApps}
          onClose={() => setImporting(false)}
        />
      )}
      {creating && canEdit && !archived && (
        <NewTaskPanel
          labId={labId}
          projectId={projectId}
          onClose={closePanel}
          document={params.get("document") ?? undefined}
          title={params.get("title") ?? undefined}
        />
      )}
      {editing && !creating && (
        <TaskDrawer
          key={editing.id}
          labId={labId}
          projectId={projectId}
          task={editing}
          assignable={assignable}
          canEdit={canEdit}
          isLead={isLead}
          onClose={() => setParam("task", null)}
          onPatch={(patch) => update.mutateAsync({ id: editing.id, patch })}
          onDelete={() => {
            remove.mutate(editing.id, {
              onSuccess: () => toast.success("Task deleted"),
              onError: () => toast.error("Couldn't delete the task, so it was put back."),
            });
            setParam("task", null);
          }}
        />
      )}
    </div>
  );
}
