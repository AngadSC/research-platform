import { CalendarClock, Sparkles } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Badge } from "@/components/ui/badge";
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
import { useAssistantReady } from "@/hooks/assistant";
import { openAssistant } from "@/lib/assistant";
import { useApprovals } from "@/hooks/ethics";
import { useLab } from "@/hooks/workspace";
import { useDeadlines, useProjectMembers, useUpdateProject } from "@/hooks/projects";
import { useFunding } from "@/hooks/workflow";
import { RoleName } from "@/components/shared/RoleName";
import { useMembers } from "@/hooks/workspace";
import {
  PROJECT_ROLES,
  PROJECT_STATUSES,
  roleLabel,
  personName,
  type Deadline,
  type DeadlinePriority,
  type ProjectMembership,
  type ProjectRole,
} from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { NativeSelect } from "@/pages/project/workflow/parts";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { FUNDING_STATUSES, label, PRIORITIES, PRIORITY_TONE } from "@/lib/workflow";

const fail = (e: unknown) => toast.error(formErrors(e, []).form ?? "Something went wrong.");
const day = (iso: string | null) =>
  iso
    ? new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { dateStyle: "medium" })
    : "Not set";

/** D19: a lab role can override the project role. Says what the person can really do, or "". */
const effectiveRoleHint = (name: string, labRole: string | undefined, role: ProjectRole) => {
  if ((labRole === "pi" || labRole === "lab_admin") && role !== "lead")
    return `${name} is a ${roleLabel(labRole)}, so they can change everything here anyway.`;
  if (labRole === "viewer" && role !== "viewer")
    return `${name} is a lab Viewer, so they can only read here.`;
  return "";
};

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm">{value}</dd>
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
  onSave: (v: { title: string; due_date: string; priority: DeadlinePriority }) => Promise<unknown>;
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
      await onSave({ title, due_date, priority: String(f.get("priority")) as DeadlinePriority });
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
          <FormField label="Priority">
            {(p) => (
              <NativeSelect {...p} name="priority" defaultValue={existing?.priority ?? "medium"}>
                {PRIORITIES.map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </NativeSelect>
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
    {
      key: "priority",
      header: "Priority",
      cell: (d) => (
        <Badge variant={PRIORITY_TONE[d.priority] ?? "secondary"}>
          {label(PRIORITIES, d.priority)}
        </Badge>
      ),
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
      <SelectTrigger
        aria-label={label}
        className="w-40"
        title={PROJECT_ROLES.find((r) => r.value === value)?.help}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {PROJECT_ROLES.map((r) => (
          <SelectItem key={r.value} value={r.value} hint={r.help}>
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
  const chosen = options.find((m) => m.user.id === user);
  const hint = chosen ? effectiveRoleHint(personName(chosen.user), chosen.role, role) : "";
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!user) return setError("Choose a person to add");
    setError(undefined);
    try {
      await onAdd({ user, role });
      toast.success("Member added");
      setUser("");
      setRole("contributor");
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
        <FormField label="Role" hint={hint || undefined}>
          {(p) => (
            <Select value={role} onValueChange={(v) => setRole(v as ProjectRole)}>
              <SelectTrigger {...p}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PROJECT_ROLES.map((r) => (
                  <SelectItem key={r.value} value={r.value} hint={r.help}>
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
  const labRoles = new Map((useMembers(labId).data ?? []).map((m) => [m.user.id, m.role]));
  const cols: Column<ProjectMembership>[] = [
    {
      key: "name",
      header: "Name",
      cell: (m) => <span className="font-medium">{personName(m.user)}</span>,
    },
    {
      key: "role",
      header: "Role",
      cell: (m) => {
        const hint = effectiveRoleHint(personName(m.user), labRoles.get(m.user.id), m.role);
        return (
          <div className="grid gap-1">
            {/* The server says per row: a lead cannot change a PI or the last lead. */}
            {canManage && m.can_change ? (
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
              <RoleName role={m.role} roles={PROJECT_ROLES} />
            )}
            {hint && <p className="max-w-56 text-xs text-muted-foreground">{hint}</p>}
          </div>
        );
      },
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
                    aria-label={`Handover for ${m.user.email}`}
                    title="Lists everything this person owns or leads in this project, so it can be given to someone else."
                  >
                    Handover
                  </Link>
                </Button>
                {m.can_change && (
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
                )}
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

function ProjectApprovals({
  labId,
  projectId,
  canLink,
}: {
  labId: string;
  projectId: string;
  canLink: boolean;
}) {
  const { data: lab } = useLab(labId);
  const { data } = useApprovals(labId, lab?.my_permissions.includes("view_ethics"));
  const mine = (data ?? []).filter((a) => a.projects.some((p) => p.id === projectId));
  if (!lab?.my_permissions.includes("view_ethics")) return null;
  return (
    <section className="grid gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">Ethics approvals</h2>
        {canLink && lab.my_permissions.includes("edit_ethics") && (
          <Button variant="outline" size="sm" asChild>
            <Link to={`/labs/${labId}/projects/${projectId}/workflow/ethics?link=1`}>
              Link an approval
            </Link>
          </Button>
        )}
      </div>
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

/** D226: rendered for PIs only, so nobody else ever asks for funding. */
function FundingSummary({ labId, projectId }: { labId: string; projectId: string }) {
  const { list } = useFunding(labId, projectId);
  const rows = list.data ?? [];
  return (
    <section className="grid gap-3" aria-labelledby="overview-funding">
      <div className="flex items-center justify-between">
        <h2 id="overview-funding" className="text-base font-semibold">
          Funding
        </h2>
        <Button variant="outline" size="sm" asChild>
          <Link
            to={`/labs/${labId}/projects/${projectId}/workflow/funding${rows.length ? "" : "?new=1"}`}
          >
            {rows.length ? "Open funding" : "Add funding"}
          </Link>
        </Button>
      </div>
      {list.isLoading ? null : rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">No funding recorded. Only PIs see this.</p>
      ) : (
        <ul className="grid divide-y rounded-lg border">
          {rows.map((f) => (
            <li key={f.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
              <span className="font-medium">
                {[f.funder, f.program].filter(Boolean).join(", ")}
              </span>
              <span className="text-muted-foreground">
                {label(FUNDING_STATUSES, f.status)}
                {f.end_date && <> · ends {day(f.end_date)}</>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** A project's lead archives it (edit_project); deleting stays with PIs and lab admins (D28). */
function ArchiveProject({
  labId,
  projectId,
  name,
  canDelete,
}: {
  labId: string;
  projectId: string;
  name: string;
  canDelete: boolean;
}) {
  const update = useUpdateProject(labId, projectId);
  const [open, setOpen] = useState(false);
  return (
    <section className="grid gap-2">
      <div>
        <Button variant="outline" onClick={() => setOpen(true)}>
          Archive project
        </Button>
      </div>
      {!canDelete && (
        <p className="text-xs text-muted-foreground">
          Archiving keeps everything, and you can reopen it by changing its status. To delete the
          project, ask a PI or lab admin.
        </p>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">Archive {name}?</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            Nothing is deleted. Set its status back to Active any time to reopen it.
          </DialogDescription>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={update.isPending}
              onClick={() =>
                update.mutate(
                  { status: "archived" },
                  {
                    onSuccess: () => {
                      toast.success("Project archived");
                      setOpen(false);
                    },
                    onError: fail,
                  },
                )
              }
            >
              Archive
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}

// Props: { labId, projectId, project } (ProjectTabProps).
export default function OverviewTab({ labId, projectId, project }: ProjectTabProps) {
  const can = (p: string) => project.my_permissions.includes(p);
  const assistantReady = useAssistantReady(labId);
  return (
    <div className="grid gap-8">
      {project.status === "archived" && (
        <p role="status" className="rounded-lg bg-muted p-3 text-sm font-medium">
          Archived. Set it back to Active to make changes.
        </p>
      )}
      {assistantReady && (
        <Button
          variant="secondary"
          className="justify-self-start"
          onClick={() =>
            openAssistant(
              `Use project_overview for project_id ${projectId} in lab ${labId}, and list_tasks for this project. In under 150 words, tell me: where the project stands, what is overdue or due in the next two weeks, and the single most useful next step. Do not change anything.`,
            )
          }
        >
          <Sparkles aria-hidden /> Catch me up
        </Button>
      )}
      <section className="grid gap-3">
        <h2 className="text-base font-semibold">About</h2>
        <p className="text-sm whitespace-pre-wrap">
          {project.description || "No description yet."}
        </p>
        {project.last_activity_at && (
          <p className="text-xs text-muted-foreground">
            Last activity <RelativeTime value={project.last_activity_at} />
            {project.last_activity_by && <> by {personName(project.last_activity_by)}</>}
          </p>
        )}
        <dl className="grid grid-cols-3 gap-4">
          <Fact
            label="Status"
            value={
              PROJECT_STATUSES.find((s) => s.value === project.status)?.label ?? project.status
            }
          />
          <Fact label="Start date" value={day(project.start_date)} />
          <Fact label="Keep until" value={day(project.retain_until)} />
        </dl>
        {project.retention_note && (
          <p className="text-xs text-muted-foreground">Retention note: {project.retention_note}</p>
        )}
      </section>
      {can("access_funding") && <FundingSummary labId={labId} projectId={projectId} />}
      <ProjectApprovals
        labId={labId}
        projectId={projectId}
        canLink={can("edit_content") && project.status !== "archived"}
      />
      <Deadlines
        labId={labId}
        projectId={projectId}
        canEdit={can("edit_project") && project.status !== "archived"}
      />
      <Members labId={labId} projectId={projectId} canManage={can("manage_project_members")} />
      {can("edit_project") && project.status !== "archived" && (
        <ArchiveProject
          labId={labId}
          projectId={projectId}
          name={project.name}
          canDelete={can("delete_project")}
        />
      )}
    </div>
  );
}
