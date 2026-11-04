import { LayoutList, ListChecks, MoreHorizontal, Plus, SquareKanban } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { DetailPanel } from "@/components/shared/DetailPanel";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useProjectMembers, useTasks } from "@/hooks/projects";
import {
  TASK_STATUSES,
  personName,
  taskStatusLabel,
  type Task,
  type TaskStatus,
} from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import type { ProjectTabProps } from "@/pages/ProjectPage";

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

function TaskPanel({
  task,
  members,
  onClose,
  onSave,
  onDelete,
}: {
  task: Task | "new";
  onDelete?: () => void;
  members: { id: string; name: string }[];
  onClose: () => void;
  onSave: (v: {
    title: string;
    description: string;
    assignee: string | null;
    due_date: string | null;
    status: TaskStatus;
  }) => Promise<unknown>;
}) {
  const existing = task === "new" ? undefined : task;
  const [status, setStatus] = useState<TaskStatus>(existing?.status ?? "todo");
  const [assignee, setAssignee] = useState(existing?.assignee?.id ?? NONE);
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const [confirmDelete, setConfirmDelete] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const title = String(f.get("title") ?? "").trim();
    if (!title) return setErrors({ fields: { title: "Enter a title" } });
    setErrors({ fields: {} });
    try {
      await onSave({
        title,
        description: String(f.get("description") ?? ""),
        assignee: assignee === NONE ? null : assignee,
        due_date: String(f.get("due_date") ?? "") || null,
        status,
      });
      toast.success("Saved");
      onClose();
    } catch (err) {
      setErrors(formErrors(err, ["title", "description", "assignee", "due_date", "status"]));
    }
  }

  return (
    <DetailPanel
      open
      onOpenChange={(o) => !o && onClose()}
      title={existing ? "Edit task" : "New task"}
    >
      <form onSubmit={submit} noValidate className="grid gap-4 py-4">
        <FormField label="Title" error={errors.fields.title}>
          {(p) => <Input {...p} name="title" defaultValue={existing?.title} autoComplete="off" />}
        </FormField>
        <FormField label="Description" error={errors.fields.description}>
          {(p) => <Textarea {...p} name="description" defaultValue={existing?.description} />}
        </FormField>
        <FormField label="Assignee" error={errors.fields.assignee}>
          {(p) => (
            <Select value={assignee} onValueChange={setAssignee}>
              <SelectTrigger {...p}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>Unassigned</SelectItem>
                {members.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </FormField>
        <FormField label="Status">
          {(p) => (
            <Select value={status} onValueChange={(v) => setStatus(v as TaskStatus)}>
              <SelectTrigger {...p}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TASK_STATUSES.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </FormField>
        <FormField label="Due date" error={errors.fields.due_date}>
          {(p) => (
            <Input {...p} type="date" name="due_date" defaultValue={existing?.due_date ?? ""} />
          )}
        </FormField>
        <FormError message={errors.form} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit">Save</Button>
        </div>
      </form>
      {existing && onDelete && (
        <div className="border-t py-4">
          {confirmDelete ? (
            <div role="alertdialog" aria-label="Confirm delete" className="grid gap-3">
              <p className="text-sm">Delete �{existing.title}�? This can't be undone.</p>
              <div className="flex gap-2">
                <Button variant="destructive" onClick={onDelete}>
                  Confirm delete
                </Button>
                <Button variant="outline" onClick={() => setConfirmDelete(false)}>
                  Keep task
                </Button>
              </div>
            </div>
          ) : (
            <Button variant="outline" onClick={() => setConfirmDelete(true)}>
              Delete task
            </Button>
          )}
        </div>
      )}
    </DetailPanel>
  );
}

function Board({
  tasks,
  canEdit,
  move,
  onOpen,
}: {
  tasks: Task[];
  canEdit: boolean;
  move: MoveFn;
  onOpen: (t: Task) => void;
}) {
  const [dragId, setDragId] = useState<string | null>(null);
  const dropAt = (status: TaskStatus, before?: Task) => {
    const dragged = tasks.find((t) => t.id === dragId);
    setDragId(null);
    if (!dragged) return;
    const col = tasks.filter((t) => t.status === status && t.id !== dragged.id);
    const at = before ? col.findIndex((t) => t.id === before.id) : col.length;
    move(dragged, status, at < 0 ? col.length : at);
  };
  return (
    <div className="grid grid-cols-3 gap-4">
      {TASK_STATUSES.map((s) => {
        const col = tasks.filter((t) => t.status === s.value);
        return (
          <section
            key={s.value}
            aria-label={s.label}
            onDragOver={canEdit ? (e) => e.preventDefault() : undefined}
            onDrop={canEdit ? () => dropAt(s.value) : undefined}
            className="flex min-h-40 flex-col gap-2 rounded-lg border bg-muted/30 p-3"
          >
            <h3 className="text-sm font-semibold">
              {s.label} <span className="font-normal text-muted-foreground">{col.length}</span>
            </h3>
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
                className="flex items-start justify-between gap-2 rounded-md border bg-background p-3"
              >
                <div className="min-w-0">
                  <button
                    type="button"
                    onClick={() => onOpen(t)}
                    className="text-left text-sm font-medium hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                  >
                    {t.title}
                  </button>
                  <p className="text-xs text-muted-foreground">
                    {[t.assignee && personName(t.assignee), day(t.due_date)]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
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
  const { list, create, update, remove, move } = useTasks(labId, projectId);
  const members = useProjectMembers(labId, projectId).list.data ?? [];
  const [params, setParams] = useSearchParams();
  const [editing, setEditing] = useState<Task | null>(null);
  const [fStatus, setFStatus] = useState("all");
  const [fAssignee, setFAssignee] = useState("all");
  const canEdit = project.my_permissions.includes("edit_content");
  const view = params.get("view") === "board" ? "board" : "list";
  const creating = params.get("new") === "task";
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
    { key: "status", header: "Status", cell: (t) => <StatusBadge status={t.status} /> },
    {
      key: "assignee",
      header: "Assignee",
      cell: (t) => (t.assignee ? personName(t.assignee) : "Unassigned"),
    },
    { key: "due", header: "Due", cell: (t) => day(t.due_date) || "No date" },
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

  const newTask = canEdit ? (
    <Button onClick={() => setParam("new", "task")}>
      <Plus aria-hidden /> New task
    </Button>
  ) : undefined;
  const empty = (
    <EmptyState
      icon={ListChecks}
      title="No tasks yet"
      description="Add a task to track what needs doing in this project."
      action={newTask}
    />
  );
  const closePanel = () => {
    setEditing(null);
    setParam("new", null);
  };

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="View" className="flex gap-1">
          <Button
            variant={view === "list" ? "secondary" : "ghost"}
            size="sm"
            aria-pressed={view === "list"}
            onClick={() => setParam("view", null)}
          >
            <LayoutList aria-hidden /> List
          </Button>
          <Button
            variant={view === "board" ? "secondary" : "ghost"}
            size="sm"
            aria-pressed={view === "board"}
            onClick={() => setParam("view", "board")}
          >
            <SquareKanban aria-hidden /> Board
          </Button>
        </div>
        {all.length > 0 && newTask}
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
          onRowClick={(t) => setEditing(t)}
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
        <Board tasks={all} canEdit={canEdit} move={doMove} onOpen={setEditing} />
      )}
      {(creating || editing) && canEdit && (
        <TaskPanel
          key={editing?.id ?? "new"}
          task={editing ?? "new"}
          members={members.map((m) => ({ id: m.user.id, name: personName(m.user) }))}
          onClose={closePanel}
          onDelete={
            editing
              ? () => {
                  remove.mutate(editing.id, {
                    onSuccess: () => toast.success("Task deleted"),
                    onError: () => toast.error("Couldn't delete the task, so it was put back."),
                  });
                  closePanel();
                }
              : undefined
          }
          onSave={(v) =>
            editing ? update.mutateAsync({ id: editing.id, patch: v }) : create.mutateAsync(v)
          }
        />
      )}
    </div>
  );
}
