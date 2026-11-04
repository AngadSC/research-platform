import { CalendarClock } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Link } from "react-router";
import { ApprovalBadge, ExpiryText } from "@/components/ethics/ApprovalBadge";
import { useApprovals } from "@/hooks/ethics";
import { useLab } from "@/hooks/workspace";
import { useDeadlines, useProjectMembers } from "@/hooks/projects";
import { useMembers } from "@/hooks/workspace";
import {
  PROJECT_ROLES,
  personName,
  type Deadline,
  type ProjectMembership,
  type ProjectRole,
} from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import type { ProjectTabProps } from "@/pages/ProjectPage";

const fail = (e: unknown) => toast.error(formErrors(e, []).form ?? "Something went wrong.");
const day = (iso: string | null) =>
  iso
    ? new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { dateStyle: "medium" })
    : "Not set";
const roleName = (r: string) => PROJECT_ROLES.find((x) => x.value === r)?.label ?? r;

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm capitalize">{value}</dd>
    </div>
  );
}

function DeadlineDialog({
  deadline,
  onClose,
  onSave,
}: {
  deadline: Deadline | "new";
  onClose: () => void;
  onSave: (v: { title: string; due_date: string }) => Promise<unknown>;
}) {
  const existing = deadline === "new" ? undefined : deadline;
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const title = String(f.get("title") ?? "").trim();
    const due_date = String(f.get("due_date") ?? "");
    const fields: Record<string, string> = {};
    if (!title) fields.title = "Enter a title";
    if (!due_date) fields.due_date = "Pick a due date";
    if (Object.keys(fields).length) return setErrors({ fields });
    try {
      await onSave({ title, due_date });
      toast.success("Saved");
      onClose();
    } catch (err) {
      setErrors(formErrors(err, ["title", "due_date"]));
    }
  }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">
          {existing ? "Edit deadline" : "Add deadline"}
        </DialogTitle>
        <DialogDescription className="sr-only">Deadline details</DialogDescription>
        <form onSubmit={submit} noValidate className="grid gap-4">
          <FormField label="Title" error={errors.fields.title}>
            {(p) => <Input {...p} name="title" defaultValue={existing?.title} autoComplete="off" />}
          </FormField>
          <FormField label="Due date" error={errors.fields.due_date}>
            {(p) => <Input {...p} type="date" name="due_date" defaultValue={existing?.due_date} />}
          </FormField>
          <FormError message={errors.form} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit">Save</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Deadlines({
  labId,
  projectId,
  canEdit,
}: {
  labId: string;
  projectId: string;
  canEdit: boolean;
}) {
  const { list, create, update, remove } = useDeadlines(labId, projectId);
  const [editing, setEditing] = useState<Deadline | "new" | null>(null);
  const cols: Column<Deadline>[] = [
    {
      key: "title",
      header: "Deadline",
      cell: (d) => <span className={d.done ? "line-through" : undefined}>{d.title}</span>,
    },
    { key: "due", header: "Due", cell: (d) => day(d.due_date) },
    ...(canEdit
      ? [
          {
            key: "actions",
            header: "Actions",
            className: "text-right",
            cell: (d: Deadline) => (
              <div className="flex justify-end gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`${d.done ? "Reopen" : "Mark done"} ${d.title}`}
                  onClick={() =>
                    update.mutate({ id: d.id, patch: { done: !d.done } }, { onError: fail })
                  }
                >
                  {d.done ? "Reopen" : "Mark done"}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Edit ${d.title}`}
                  onClick={() => setEditing(d)}
                >
                  Edit
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove ${d.title}`}
                  onClick={() =>
                    remove.mutate(d.id, {
                      onSuccess: () => toast.success("Deadline removed"),
                      onError: fail,
                    })
                  }
                >
                  Remove
                </Button>
              </div>
            ),
          },
        ]
      : []),
  ];
  return (
    <section className="grid gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">Deadlines</h2>
        {canEdit && (
          <Button variant="outline" size="sm" onClick={() => setEditing("new")}>
            Add deadline
          </Button>
        )}
      </div>
      <DataTable
        columns={cols}
        rows={list.data ?? []}
        getRowKey={(d) => d.id}
        loading={list.isLoading}
        empty={
          <EmptyState
            icon={CalendarClock}
            title="No deadlines"
            description="Add dates your team needs to hit."
          />
        }
      />
      {editing && (
        <DeadlineDialog
          deadline={editing}
          onClose={() => setEditing(null)}
          onSave={(v) =>
            editing === "new"
              ? create.mutateAsync(v)
              : update.mutateAsync({ id: editing.id, patch: v })
          }
        />
      )}
    </section>
  );
}

function RoleSelect({
  value,
  onChange,
  label,
}: {
  value: ProjectRole;
  onChange: (r: ProjectRole) => void;
  label: string;
}) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as ProjectRole)}>
      <SelectTrigger aria-label={label} className="w-40">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {PROJECT_ROLES.map((r) => (
          <SelectItem key={r.value} value={r.value}>
            {r.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function AddMember({
  labId,
  existing,
  onAdd,
}: {
  labId: string;
  existing: Set<string>;
  onAdd: (v: { user: string; role: ProjectRole }) => Promise<unknown>;
}) {
  const labMembers = useMembers(labId);
  const [user, setUser] = useState("");
  const [role, setRole] = useState<ProjectRole>("contributor");
  const [error, setError] = useState<string>();
  const options = (labMembers.data ?? []).filter((m) => !existing.has(m.user.id));
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!user) return setError("Choose a person to add");
    setError(undefined);
    try {
      await onAdd({ user, role });
      toast.success("Member added");
      setUser("");
    } catch (err) {
      setError(formErrors(err, []).form);
    }
  }
  return (
    <form
      onSubmit={submit}
      noValidate
      aria-label="Add a member"
      className="flex flex-wrap items-start gap-3"
    >
      <div className="w-64">
        <FormField label="Person" error={error}>
          {(p) => (
            <Select value={user} onValueChange={setUser}>
              <SelectTrigger {...p}>
                <SelectValue placeholder="Choose a lab member" />
              </SelectTrigger>
              <SelectContent>
                {options.map((m) => (
                  <SelectItem key={m.user.id} value={m.user.id}>
                    {personName(m.user)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </FormField>
      </div>
      <div className="w-44">
        <FormField label="Role">
          {(p) => (
            <Select value={role} onValueChange={(v) => setRole(v as ProjectRole)}>
              <SelectTrigger {...p}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PROJECT_ROLES.map((r) => (
                  <SelectItem key={r.value} value={r.value}>
                    {r.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </FormField>
      </div>
      <Button type="submit" className="mt-[1.375rem]">
        Add member
      </Button>
    </form>
  );
}

function Members({
  labId,
  projectId,
  canManage,
}: {
  labId: string;
  projectId: string;
  canManage: boolean;
}) {
  const { list, create, update, remove } = useProjectMembers(labId, projectId);
  const cols: Column<ProjectMembership>[] = [
    {
      key: "name",
      header: "Name",
      cell: (m) => <span className="font-medium">{personName(m.user)}</span>,
    },
    {
      key: "role",
      header: "Role",
      cell: (m) =>
        canManage ? (
          <RoleSelect
            label={`Role for ${m.user.email}`}
            value={m.role}
            onChange={(role) =>
              update.mutate(
                { id: m.id, patch: { role } },
                { onSuccess: () => toast.success("Saved"), onError: fail },
              )
            }
          />
        ) : (
          roleName(m.role)
        ),
    },
    ...(canManage
      ? [
          {
            key: "actions",
            header: "Actions",
            className: "text-right",
            cell: (m: ProjectMembership) => (
              <div className="flex justify-end gap-1">
                <Button variant="ghost" size="sm" asChild>
                  <Link
                    to={`/labs/${labId}/projects/${projectId}/handover?user=${m.user.id}`}
                    aria-label={`Generate handover for ${m.user.email}`}
                  >
                    Generate handover
                  </Link>
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove ${m.user.email}`}
                  onClick={() =>
                    remove.mutate(m.id, {
                      onSuccess: () => toast.success("Member removed"),
                      onError: fail,
                    })
                  }
                >
                  Remove
                </Button>
              </div>
            ),
          },
        ]
      : []),
  ];
  return (
    <section className="grid gap-3">
      <h2 className="text-base font-semibold">Members</h2>
      {canManage && (
        <AddMember
          labId={labId}
          existing={new Set((list.data ?? []).map((m) => m.user.id))}
          onAdd={(v) => create.mutateAsync(v)}
        />
      )}
      <DataTable
        columns={cols}
        rows={list.data ?? []}
        getRowKey={(m) => m.id}
        loading={list.isLoading}
        empty={
          <EmptyState
            title="No members yet"
            description="People added to this project can be assigned tasks."
          />
        }
      />
    </section>
  );
}

function ProjectApprovals({ labId, projectId }: { labId: string; projectId: string }) {
  const { data: lab } = useLab(labId);
  const { data } = useApprovals(labId, lab?.my_permissions.includes("view_ethics"));
  const mine = (data ?? []).filter((a) => a.projects.some((p) => p.id === projectId));
  if (!lab?.my_permissions.includes("view_ethics")) return null;
  return (
    <section className="grid gap-3">
      <h2 className="text-base font-semibold">Ethics approvals</h2>
      {mine.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No ethics approvals are linked to this project.
        </p>
      ) : (
        <ul className="grid divide-y rounded-lg border">
          {mine.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
              <Link to={`/labs/${labId}/ethics/${a.id}`} className="font-medium hover:underline">
                {a.approval_number}: {a.title}
              </Link>
              <span className="flex items-center gap-2">
                <ExpiryText expiry={a.expiry_date} />
                <ApprovalBadge status={a.status} expiry={a.expiry_date} />
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// Props: { labId, projectId, project } (ProjectTabProps).
export default function OverviewTab({ labId, projectId, project }: ProjectTabProps) {
  const can = (p: string) => project.my_permissions.includes(p);
  return (
    <div className="grid gap-8">
      <section className="grid gap-3">
        <h2 className="text-base font-semibold">About</h2>
        <p className="text-sm whitespace-pre-wrap">
          {project.description || "No description yet."}
        </p>
        <dl className="grid grid-cols-3 gap-4">
          <Fact label="Status" value={project.status} />
          <Fact label="Start date" value={day(project.start_date)} />
          <Fact label="Keep until" value={day(project.retain_until)} />
        </dl>
        {project.retention_note && (
          <p className="text-xs text-muted-foreground">Retention note: {project.retention_note}</p>
        )}
      </section>
      <ProjectApprovals labId={labId} projectId={projectId} />
      <Deadlines labId={labId} projectId={projectId} canEdit={can("edit_project")} />
      <Members labId={labId} projectId={projectId} canManage={can("manage_project_members")} />
    </div>
  );
}
