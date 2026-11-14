import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { DetailPanel } from "@/components/shared/DetailPanel";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
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
import { useDocuments } from "@/hooks/documents";
import { useProjectMembers, useTasks } from "@/hooks/projects";
import { api } from "@/lib/api";
import { TASK_STATUSES, personName, type TaskStatus } from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";

const NONE = "none";

/** The "New task" side panel. Used on the Tasks tab and, with `document` set, from a document
 * ("Add a task from this document"), where the task starts out linked to it. */
export function NewTaskPanel({
  labId,
  projectId,
  onClose,
  document,
  title: initialTitle = "",
}: {
  labId: string;
  projectId: string;
  onClose: () => void;
  /** Document to link the new task to. The person can change or clear it. */
  document?: string;
  title?: string;
}) {
  const { create } = useTasks(labId, projectId);
  const qc = useQueryClient();
  const members = (useProjectMembers(labId, projectId).list.data ?? [])
    .filter((m) => m.role !== "viewer")
    .map((m) => ({ id: m.user.id, name: personName(m.user) }));
  const docs = useDocuments(labId, projectId).data ?? [];
  const [status, setStatus] = useState<TaskStatus>("todo");
  const [assignee, setAssignee] = useState(NONE);
  const [linked, setLinked] = useState(document ?? NONE);
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const title = String(f.get("title") ?? "").trim();
    if (!title) return setErrors({ fields: { title: "Enter a title" } });
    setErrors({ fields: {} });
    try {
      const task = await create.mutateAsync({
        title,
        description: String(f.get("description") ?? ""),
        assignee: assignee === NONE ? null : assignee,
        due_date: String(f.get("due_date") ?? "") || null,
        status,
      });
      if (linked !== NONE) {
        try {
          await api(`/api/labs/${labId}/tasks/${task.id}/documents/`, {
            method: "POST",
            body: { id: linked },
          });
          void qc.invalidateQueries({ queryKey: ["labs", labId, "projects", projectId, "tasks"] });
        } catch {
          toast.error("The task was saved, but it could not be linked to the document.");
          return onClose();
        }
      }
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
      title="New task"
      description="Add what needs doing. Assignee and due date are optional."
    >
      <form onSubmit={submit} noValidate className="grid gap-4 py-4">
        <FormField label="Title" error={errors.fields.title}>
          {(p) => (
            <Input
              {...p}
              name="title"
              autoComplete="off"
              maxLength={300}
              defaultValue={initialTitle}
            />
          )}
        </FormField>
        <FormField label="Description" error={errors.fields.description}>
          {(p) => <Textarea {...p} name="description" />}
        </FormField>
        <FormField label="Document">
          {(p) => (
            <Select value={linked} onValueChange={setLinked}>
              <SelectTrigger {...p}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>No document</SelectItem>
                {docs.map((d) => (
                  <SelectItem key={d.id} value={d.id}>
                    {d.title}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
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
          {(p) => <Input {...p} type="date" name="due_date" />}
        </FormField>
        <FormError message={errors.form} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={create.isPending}>
            Save
          </Button>
        </div>
      </form>
    </DetailPanel>
  );
}
