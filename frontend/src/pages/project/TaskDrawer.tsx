import { useRef, useState, type FocusEvent } from "react";
import { Clock } from "lucide-react";
import { toast } from "sonner";
import { DetailPanel } from "@/components/shared/DetailPanel";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { UserAvatar } from "@/components/shared/UserAvatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  TASK_STATUSES,
  personName,
  taskStatusLabel,
  type Task,
  type TaskInput,
  type TaskStatus,
} from "@/lib/api-types";
import { shortDate } from "@/lib/dashboard";
import { formErrors, type FormErrors } from "@/lib/forms";
import { localDateISO } from "@/lib/format";
import { nextMonday } from "@/lib/snooze";
import { TaskFiles } from "@/pages/project/TaskFiles";
import { TaskThread } from "@/pages/project/TaskThread";

export const NONE = "none";
export interface Assignable {
  id: string;
  name: string;
}

/** The task detail drawer (Run 4): details, status, assignee, delete, files and the update
 * thread. Anyone who can view the project can open it; the controls need edit_content. */
export function TaskDrawer({
  labId,
  projectId,
  task,
  assignable,
  canEdit,
  isLead,
  onClose,
  onPatch,
  onDelete,
}: {
  labId: string;
  projectId: string;
  task: Task;
  /** People who can be assigned (edit_content on the project). */
  assignable: Assignable[];
  canEdit: boolean;
  isLead: boolean;
  onClose: () => void;
  onPatch: (patch: Partial<TaskInput>) => Promise<unknown>;
  onDelete: () => void;
}) {
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const [confirmDelete, setConfirmDelete] = useState(false);
  const current = task.assignee
    ? assignable.some((a) => a.id === task.assignee!.id)
      ? assignable
      : [...assignable, { id: task.assignee.id, name: personName(task.assignee) }]
    : assignable;

  async function patch(p: Partial<TaskInput>, ok = "Saved") {
    try {
      await onPatch(p);
      setErrors({ fields: {} });
      toast.success(ok);
    } catch (err) {
      const e = formErrors(err, ["title", "description", "assignee", "due_date", "status"]);
      setErrors(e);
      toast.error(Object.values(e.fields)[0] ?? e.form ?? "Something went wrong.");
    }
  }

  // Title, description and due date save when you leave the field, like status and assignee.
  function saveField(e: FocusEvent<HTMLInputElement | HTMLTextAreaElement>) {
    const { name, value } = e.currentTarget;
    if (name === "title") {
      const title = value.trim();
      if (!title) return setErrors({ fields: { title: "Enter a title" } });
      if (title !== task.title) void patch({ title });
    } else if (name === "description") {
      if (value !== task.description) void patch({ description: value });
    } else if ((value || null) !== task.due_date) void patch({ due_date: value || null });
  }

  // The panel focuses its first field and selects it; put the cursor at the end instead, so a
  // stray keypress doesn't replace the title.
  const firstFocus = useRef(true);
  function unselect(e: FocusEvent<HTMLInputElement>) {
    if (!firstFocus.current) return;
    firstFocus.current = false;
    const el = e.currentTarget;
    setTimeout(() => el.setSelectionRange(el.value.length, el.value.length), 0);
  }

  return (
    <DetailPanel open onOpenChange={(o) => !o && onClose()} title={task.title}>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-5 py-4">
        {canEdit ? (
          <>
            <form
              onSubmit={(e) => e.preventDefault()}
              noValidate
              className="grid gap-3"
              aria-label="Task details"
            >
              <FormField label="Title" error={errors.fields.title}>
                {(p) => (
                  <Input
                    maxLength={300}
                    {...p}
                    name="title"
                    defaultValue={task.title}
                    autoComplete="off"
                    onFocus={unselect}
                    onBlur={saveField}
                  />
                )}
              </FormField>
              <FormField label="Description" error={errors.fields.description}>
                {(p) => (
                  <Textarea
                    {...p}
                    name="description"
                    defaultValue={task.description}
                    onBlur={saveField}
                  />
                )}
              </FormField>
              <FormField label="Due date" error={errors.fields.due_date}>
                {(p) => (
                  <Input
                    {...p}
                    type="date"
                    name="due_date"
                    defaultValue={task.due_date ?? ""}
                    onBlur={saveField}
                  />
                )}
              </FormField>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                {task.snoozed_until && task.snoozed_until > localDateISO() ? (
                  <>
                    <span className="text-muted-foreground">
                      Snoozed until {shortDate(task.snoozed_until)}
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => void patch({ snoozed_until: null }, "Snooze removed")}
                    >
                      Wake it now
                    </Button>
                  </>
                ) : (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      void patch(
                        { snoozed_until: nextMonday(localDateISO()) },
                        "Snoozed until Monday",
                      )
                    }
                  >
                    <Clock aria-hidden /> Snooze until Monday
                  </Button>
                )}
              </div>
              <FormError message={errors.form} />
            </form>
            <div className="grid grid-cols-2 gap-3">
              <FormField label="Status" error={errors.fields.status}>
                {(p) => (
                  <Select
                    value={task.status}
                    onValueChange={(v) =>
                      void patch({ status: v as TaskStatus }, `Moved to ${taskStatusLabel(v)}`)
                    }
                  >
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
              <FormField label="Assignee" error={errors.fields.assignee}>
                {(p) => (
                  <Select
                    value={task.assignee?.id ?? NONE}
                    onValueChange={(v) =>
                      void patch({ assignee: v === NONE ? null : v }, "Assignee changed")
                    }
                  >
                    <SelectTrigger {...p}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={NONE}>Unassigned</SelectItem>
                      {current.map((m) => (
                        <SelectItem key={m.id} value={m.id}>
                          {m.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              </FormField>
            </div>
          </>
        ) : (
          <dl className="grid gap-2 text-sm">
            <div>
              <dt className="text-muted-foreground">Status</dt>
              <dd>{taskStatusLabel(task.status)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Assignee</dt>
              <dd className="flex items-center gap-2">
                {task.assignee ? (
                  <>
                    <UserAvatar user={task.assignee} className="size-6 text-[10px]" />
                    {personName(task.assignee)}
                  </>
                ) : (
                  "Unassigned"
                )}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Due date</dt>
              <dd>{task.due_date ?? "No date"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Description</dt>
              <dd className="whitespace-pre-wrap">{task.description || "No description"}</dd>
            </div>
          </dl>
        )}
        <TaskFiles labId={labId} projectId={projectId} task={task} canEdit={canEdit} />
        <TaskThread
          labId={labId}
          projectId={projectId}
          taskId={task.id}
          canPost={canEdit}
          isLead={isLead}
        />
        {canEdit && (
          <div className="border-t pt-4">
            {confirmDelete ? (
              <div role="alertdialog" aria-label="Confirm delete" className="grid gap-3">
                <p className="text-sm">Delete “{task.title}”? This can&apos;t be undone.</p>
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
      </div>
    </DetailPanel>
  );
}
