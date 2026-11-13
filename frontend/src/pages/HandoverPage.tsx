import { AlertTriangle, Printer } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { addProjectLead, reassignDataset, reassignTask, useHandover } from "@/hooks/handover";
import { useProject } from "@/hooks/projects";
import { useLab, useMembers } from "@/hooks/workspace";
import type { HandoverItem } from "@/lib/api-types";
import { personName } from "@/lib/api-types";
import { ApiError } from "@/lib/api";
import { formErrors } from "@/lib/forms";

const EMPTY: Record<string, string> = {
  open_tasks: "No open tasks are assigned to them.",
  unassigned_tasks: "No tasks were unassigned from them after an access change.",
  documents: "They have not created or last edited any documents.",
  analyses: "They have not run any analyses.",
  results: "None of their analyses have results.",
  datasets: "They do not control any datasets.",
  decisions: "They have not recorded any decisions.",
  ethics_approvals: "No ethics approvals are linked to projects they lead.",
  projects_led: "They do not lead any projects.",
  external_links: "They have not linked any outside files.",
};

type Person = { id: string; name: string };
type Errors = Record<string, string>;

const message = (e: unknown) => {
  const f = formErrors(e, ["assignee", "controlled_by", "user", "role"]);
  return Object.values(f.fields)[0] ?? f.form ?? "Something went wrong. Please try again.";
};

function PersonPicker({
  label,
  people,
  value,
  onChange,
}: {
  label: string;
  people: Person[];
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger aria-label={label} className="h-8 w-44">
        <SelectValue placeholder="Choose a person" />
      </SelectTrigger>
      <SelectContent>
        {people.map((p) => (
          <SelectItem key={p.id} value={p.id}>
            {p.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** A picker and a button. Used per row and, with a loop behind `run`, per section. */
function PickAndGo({
  label,
  button,
  people,
  run,
  progress,
}: {
  label: string;
  button: string;
  people: Person[];
  run: (userId: string) => Promise<void>;
  progress?: string;
}) {
  const [who, setWho] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex items-center gap-2 print:hidden">
      <PersonPicker label={label} people={people} value={who} onChange={setWho} />
      <Button
        size="sm"
        variant="outline"
        disabled={!who || busy}
        onClick={async () => {
          setBusy(true);
          try {
            await run(who);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy && progress ? progress : button}
      </Button>
    </div>
  );
}

function Items({
  items,
  showReason = true,
  action,
  errors = {},
}: {
  items: HandoverItem[];
  showReason?: boolean;
  action?: (i: HandoverItem) => ReactNode;
  errors?: Errors;
}) {
  return (
    <ul className="grid divide-y rounded-lg border bg-background">
      {items.map((i) => (
        <li key={`${i.kind}-${i.id}`} className="grid gap-1 px-3 py-2 text-sm">
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
            <div className="flex flex-wrap items-baseline gap-x-4">
              <Link to={i.href} className="font-medium hover:underline">
                {i.title}
              </Link>
              <span className="text-xs text-muted-foreground">
                {[
                  i.project?.name,
                  showReason
                    ? i.reason.replace(
                        /\(([a-z]+(?:_[a-z]+)*)\)$/,
                        (_, v: string) => `(${v === "todo" ? "to do" : v.replace(/_/g, " ")})`,
                      )
                    : null,
                ]
                  .filter(Boolean)
                  .join(" | ")}
              </span>
            </div>
            {action?.(i)}
          </div>
          {errors[i.id] && (
            <p role="alert" className="text-xs text-destructive print:hidden">
              {errors[i.id]}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}

function HandoverSkeleton() {
  return (
    <div className="grid gap-6" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-16 w-full" />
      {[0, 1, 2].map((n) => (
        <div key={n} className="grid gap-3">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-24 w-full" />
        </div>
      ))}
    </div>
  );
}

/** Handover report for a person, lab-wide (`/members/:membershipId/handover`) or for one
 * project (`/projects/:projectId/handover?user=<id>`). */
export function HandoverPage() {
  const { labId = "", membershipId, projectId } = useParams();
  const [search] = useSearchParams();
  const user = search.get("user");
  const path = membershipId
    ? `/api/labs/${labId}/members/${membershipId}/handover/`
    : `/api/labs/${labId}/projects/${projectId}/handover/${user ? `?user=${user}` : ""}`;
  const { data, isLoading, error } = useHandover(path);
  const qc = useQueryClient();
  const lab = useLab(labId);
  const project = useProject(labId, membershipId ? undefined : projectId);
  const members = useMembers(labId);
  const [errors, setErrors] = useState<Errors>({});

  if (isLoading) return <HandoverSkeleton />;
  if (error || !data) {
    const denied = error instanceof ApiError && error.status === 403;
    return (
      <EmptyState
        title="This list is unavailable"
        description={
          denied
            ? "You do not have permission to see this list."
            : "We could not make this list. Try again."
        }
      />
    );
  }
  // The server still checks every change; this only hides buttons that would be refused.
  const canAct = membershipId
    ? !!lab.data?.my_permissions.includes("manage_members")
    : !!project.data?.my_permissions.includes("manage_project_members");
  const people: Person[] = (members.data ?? [])
    .filter((m) => m.user.id !== data.person.id && m.role !== "viewer")
    .map((m) => ({ id: m.user.id, name: personName(m.user) }));
  const nameOf = (id: string) => people.find((p) => p.id === id)?.name ?? "them";
  const refresh = () => qc.invalidateQueries({ queryKey: ["handover"] });
  const setError = (id: string, msg: string | null) =>
    setErrors((cur) => {
      const next = { ...cur };
      if (msg) next[id] = msg;
      else delete next[id];
      return next;
    });

  const change = (i: HandoverItem, userId: string) =>
    i.kind === "dataset"
      ? reassignDataset(labId, i.id, userId)
      : i.kind === "task"
        ? reassignTask(labId, i.id, userId)
        : addProjectLead(labId, i.project?.id ?? i.id, userId);
  /** Runs one change; returns true when it worked. Failures stay on the row. */
  const attempt = async (i: HandoverItem, userId: string) => {
    try {
      await change(i, userId);
      setError(i.id, null);
      return true;
    } catch (e) {
      setError(i.id, message(e));
      return false;
    }
  };
  const rowAction = (i: HandoverItem) => {
    const lead = i.kind === "project";
    if (!canAct || !["task", "dataset", "project"].includes(i.kind)) return null;
    return (
      <PickAndGo
        label={lead ? `Add a lead for ${i.title}` : `Reassign ${i.title} to`}
        button={lead ? "Add as lead" : "Reassign"}
        people={people}
        run={async (userId) => {
          if (await attempt(i, userId)) {
            toast.success(
              lead ? `${nameOf(userId)} is now a lead` : `Reassigned to ${nameOf(userId)}`,
            );
            await refresh();
          }
        }}
      />
    );
  };
  const bulk = async (items: HandoverItem[], userId: string) => {
    let ok = 0;
    for (const i of items) if (await attempt(i, userId)) ok += 1;
    const failed = items.length - ok;
    const noun = `${ok} task${ok === 1 ? "" : "s"}`;
    if (failed) toast.error(`${ok} reassigned, ${failed} failed`);
    else toast.success(`Reassigned ${noun} to ${nameOf(userId)}`);
    await refresh();
  };

  const date = new Date(data.generated_at).toLocaleDateString(undefined, { dateStyle: "long" });
  const scope = data.project ? `Limited to ${data.project.name}.` : "Everything you can see.";
  return (
    <div className="grid gap-6">
      <PageHeader
        title={`Handover for ${personName({ display_name: data.person.display_name, email: data.person.email })}`}
        description={`Everything this person owns or leads, so it can be given to someone else when they leave. Made ${date}. ${scope}`}
        actions={
          <Button variant="outline" className="print:hidden" onClick={() => window.print()}>
            <Printer className="size-4" aria-hidden /> Print or save as PDF
          </Button>
        }
      />
      {data.no_other_owner.length > 0 && (
        <section
          aria-labelledby="no-other-owner"
          className="grid gap-3 rounded-lg border border-warning/30 bg-warning/10 p-4"
        >
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 size-5 text-warning-text" aria-hidden />
            <div>
              <h2 id="no-other-owner" className="text-base font-semibold">
                No other owner ({data.no_other_owner.length})
              </h2>
              <p className="text-sm text-muted-foreground">
                These items need a new owner before this person leaves.
              </p>
            </div>
          </div>
          <Items items={data.no_other_owner} action={rowAction} errors={errors} />
        </section>
      )}
      {data.sections.map((s) => {
        const isTasks = s.key === "open_tasks" || s.key === "unassigned_tasks";
        return (
          <section key={s.key} aria-labelledby={`h-${s.key}`} className="grid gap-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 id={`h-${s.key}`} className="text-base font-semibold">
                {s.label} ({s.items.length})
              </h2>
              {canAct && isTasks && s.items.length > 0 && (
                <PickAndGo
                  label={`Reassign all ${s.label.toLowerCase()} to`}
                  button="Reassign all to…"
                  progress="Reassigning…"
                  people={people}
                  run={(userId) => bulk(s.items, userId)}
                />
              )}
            </div>
            {s.items.length ? (
              <Items items={s.items} action={rowAction} errors={errors} />
            ) : (
              <EmptyState
                className="py-6"
                title={`No ${s.label.toLowerCase()}`}
                description={EMPTY[s.key] ?? "Nothing to hand over."}
              />
            )}
          </section>
        );
      })}
    </div>
  );
}
