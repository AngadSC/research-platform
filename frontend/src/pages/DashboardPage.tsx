import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  CircleAlert,
  FolderKanban,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import { ContributionGraph } from "@/components/dashboard/ContributionGraph";
import { GettingStarted } from "@/components/dashboard/GettingStarted";
import { FormError } from "@/components/shared/FormError";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { Recents } from "@/components/shared/Recents";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useDashboard,
  useTrainingExpiring,
  type DashPerson,
  type DashProject,
} from "@/hooks/dashboard";
import { useLab } from "@/hooks/workspace";
import { roleLabel } from "@/lib/api-types";
import { daysUntil } from "@/lib/ethics";
import { dueText, HEALTH_LABEL, shortDate, sortProjects, type SortKey } from "@/lib/dashboard";
import { formErrors } from "@/lib/forms";
import { plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import { MyTasksList } from "@/pages/MyTasksPage";

type Tone = "red" | "amber" | "green";
// Colour is never the only signal: every tone also has an icon and text.
const TONE_TEXT: Record<Tone, string> = {
  red: "text-danger-text",
  amber: "text-warning-text",
  green: "text-success-text",
};
const TONE_EDGE = { red: "border-danger/50 bg-danger/5", amber: "border-warning/60 bg-warning/5" };
const TONE_ICON: Record<Tone, LucideIcon> = {
  red: CircleAlert,
  amber: AlertTriangle,
  green: CheckCircle2,
};

/** One kind of problem. A kind with nothing wrong is not shown at all. */
function Card({
  id,
  title,
  tone,
  total,
  shown,
  children,
}: {
  id: string;
  title: string;
  tone: "red" | "amber";
  total: number;
  shown: number;
  children: ReactNode;
}) {
  if (total === 0) return null;
  const Icon = TONE_ICON[tone];
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className={cn("rounded-lg border p-4", TONE_EDGE[tone])}
    >
      <h3
        id={`${id}-title`}
        className={cn("flex items-center gap-2 text-sm font-semibold", TONE_TEXT[tone])}
      >
        <Icon className="size-4" aria-hidden />
        {title}
        <span className="ml-auto tabular-nums">{total}</span>
      </h3>
      <ul className="mt-3 grid gap-2 text-sm">{children}</ul>
      {total > shown && (
        <p className="mt-3 text-xs text-muted-foreground">
          Showing {shown} of {total}.
        </p>
      )}
    </section>
  );
}

function Item({
  to,
  title,
  meta,
  tone,
  badge,
}: {
  to: string;
  title: string;
  meta: string;
  tone: Tone;
  badge?: ReactNode;
}) {
  return (
    <li className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <Link to={to} className="font-medium underline-offset-2 hover:underline">
          {title}
        </Link>
        <p className={cn("text-xs", TONE_TEXT[tone])}>{meta}</p>
      </div>
      {badge}
    </li>
  );
}

const priorityBadge = (p: string) => (
  <Badge variant={p === "high" ? "destructive" : p === "medium" ? "warning" : "success"}>{p}</Badge>
);

function Health({ p }: { p: DashProject }) {
  const Icon = TONE_ICON[p.health];
  return (
    <span
      title={p.health_reasons.join(". ") || "No problems found"}
      className={cn("inline-flex items-center gap-1 font-medium", TONE_TEXT[p.health])}
    >
      <Icon className="size-4" aria-hidden />
      {HEALTH_LABEL[p.health]}
    </span>
  );
}

const COLUMNS: { key: SortKey; header: string; right?: boolean }[] = [
  { key: "name", header: "Project" },
  { key: "status", header: "Status" },
  { key: "health", header: "Health" },
  { key: "open", header: "Open", right: true },
  { key: "overdue", header: "Overdue", right: true },
  { key: "in_progress", header: "In progress", right: true },
  { key: "deadline", header: "Next deadline" },
  { key: "edited", header: "Last edited" },
  { key: "funding", header: "Funding ends" },
];

function ProjectTable({
  labId,
  projects,
  seesFunding,
}: {
  labId: string;
  projects: DashProject[];
  /** Funding is PIs only (D226); a lab admin would otherwise read "No funding" on every row. */
  seesFunding: boolean;
}) {
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({
    key: "health",
    dir: "asc",
  });
  const rows = useMemo(() => sortProjects(projects, sort.key, sort.dir), [projects, sort]);
  const toggle = (key: SortKey) =>
    setSort((s) => ({ key, dir: s.key === key && s.dir === "asc" ? "desc" : "asc" }));

  if (projects.length === 0)
    return (
      <EmptyState
        icon={FolderKanban}
        title="No projects yet"
        description="Create a project and it will show up here with its health at a glance."
        action={
          <Button asChild>
            <Link to={`/labs/${labId}/projects?new=project`}>New project</Link>
          </Button>
        }
      />
    );

  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {COLUMNS.filter((c) => seesFunding || c.key !== "funding").map((c) => {
              const active = sort.key === c.key;
              return (
                <TableHead
                  key={c.key}
                  aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"}
                  className={c.right ? "text-right" : undefined}
                >
                  <button
                    type="button"
                    onClick={() => toggle(c.key)}
                    className="inline-flex items-center gap-1 rounded-sm font-medium hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {c.header}
                    {active &&
                      (sort.dir === "asc" ? (
                        <ArrowUp className="size-3" aria-hidden />
                      ) : (
                        <ArrowDown className="size-3" aria-hidden />
                      ))}
                  </button>
                </TableHead>
              );
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((p) => (
            <TableRow key={p.id}>
              <TableCell className="min-w-40">
                <Link
                  to={`/labs/${labId}/projects/${p.id}`}
                  className="font-medium underline-offset-2 hover:underline"
                >
                  {p.name}
                </Link>
                <p className="text-xs text-muted-foreground">
                  {p.leads.length ? p.leads.map((l) => l.name).join(", ") : "No project lead"}
                </p>
              </TableCell>
              <TableCell>
                <StatusBadge status={p.status} />
              </TableCell>
              <TableCell>
                <Health p={p} />
              </TableCell>
              <TableCell className="text-right tabular-nums">{p.open_tasks}</TableCell>
              <TableCell
                className={cn(
                  "text-right tabular-nums",
                  p.overdue_tasks > 0 && "font-semibold text-danger-text",
                )}
              >
                {p.overdue_tasks}
              </TableCell>
              <TableCell className="text-right tabular-nums">{p.in_progress_tasks}</TableCell>
              <TableCell className="min-w-40">
                {p.next_deadline ? (
                  <>
                    <span className="flex items-center gap-1.5">
                      {p.next_deadline.title}
                      {priorityBadge(p.next_deadline.priority)}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {shortDate(p.next_deadline.due_date)}
                    </span>
                  </>
                ) : (
                  <span className="text-muted-foreground">None</span>
                )}
              </TableCell>
              <TableCell className="min-w-32">
                {p.last_activity_at ? (
                  <>
                    <RelativeTime value={p.last_activity_at} />
                    {p.last_activity_by && (
                      <p className="text-xs text-muted-foreground">by {p.last_activity_by.name}</p>
                    )}
                  </>
                ) : (
                  <span className="text-muted-foreground">No edits yet</span>
                )}
              </TableCell>
              {seesFunding && (
                <TableCell className="min-w-28">
                  {p.funding_end_date ? (
                    <>
                      {shortDate(p.funding_end_date)}
                      <p className="text-xs text-muted-foreground capitalize">{p.funding_status}</p>
                    </>
                  ) : (
                    <span className="text-muted-foreground">No funding</span>
                  )}
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function PeopleTable({ people }: { people: DashPerson[] }) {
  const rows = [...people].sort(
    (a, b) => b.overdue_tasks - a.overdue_tasks || a.name.localeCompare(b.name),
  );
  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>Member</TableHead>
            <TableHead>Role</TableHead>
            <TableHead className="text-right">Open</TableHead>
            <TableHead className="text-right">Overdue</TableHead>
            <TableHead className="text-right">Done in 30 days</TableHead>
            <TableHead>Last active</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((p) => (
            <TableRow key={p.user_id}>
              <TableCell className="font-medium">{p.name}</TableCell>
              <TableCell>{roleLabel(p.role)}</TableCell>
              <TableCell className="text-right tabular-nums">{p.open_tasks}</TableCell>
              <TableCell
                className={cn(
                  "text-right tabular-nums",
                  p.overdue_tasks > 0 && "font-semibold text-danger-text",
                )}
              >
                {p.overdue_tasks}
              </TableCell>
              <TableCell className="text-right tabular-nums">{p.done_last_30_days}</TableCell>
              <TableCell>
                {p.last_active_at ? (
                  <RelativeTime value={p.last_active_at} />
                ) : (
                  <span className="text-muted-foreground">No activity yet</span>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading dashboard" className="grid gap-8">
      <div className="grid gap-3 md:grid-cols-2">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-36" />
        ))}
      </div>
      <Skeleton className="h-64" />
    </div>
  );
}

/** Home, for everyone: PIs and lab admins see how the lab stands (D171), others their own tasks. */
export function DashboardPage() {
  const { labId = "" } = useParams();
  const { data: lab, error: labError } = useLab(labId);
  const allowed = lab?.my_permissions.includes("manage_lab") ?? false;
  const { data, error, isLoading } = useDashboard(labId, allowed);
  const training = useTrainingExpiring(labId, allowed);
  const base = `/labs/${labId}`;

  const failure = labError ?? error;
  if (failure) return <FormError message={formErrors(failure, []).form} />;

  const header = (
    <>
      <PageHeader
        title="Home"
        description={lab && `${lab.name} · You are ${roleLabel(lab.my_role ?? "")}`}
      />
      <GettingStarted labId={labId} />
      <Recents />
    </>
  );
  if (lab && !allowed)
    return (
      <>
        {header}
        <section aria-labelledby="my-tasks" className="grid gap-3">
          <h2 id="my-tasks" className="text-base font-semibold">
            My tasks
          </h2>
          <MyTasksList labId={labId} />
        </section>
      </>
    );

  const a = data?.attention;
  const tr = training.data;
  const problems =
    a &&
    [
      a.overdue_tasks,
      a.ethics,
      a.funding,
      a.deadlines,
      a.stalled,
      a.unassigned,
      a.integrations,
      a.dmp ?? { total: 0 },
    ].some((group) => group.total > 0);

  return (
    <>
      {header}
      {isLoading || training.isLoading || !data || !a ? (
        <DashboardSkeleton />
      ) : (
        <div className="grid gap-8">
          {!problems && !tr?.count ? (
            <p
              role="status"
              className="flex items-center gap-2 text-sm font-medium text-success-text"
            >
              <CheckCircle2 className="size-4" aria-hidden />
              All clear. Nothing needs attention right now.
            </p>
          ) : (
            <section aria-labelledby="attention" className="grid gap-3">
              <h2 id="attention" className="text-base font-semibold">
                Needs attention
              </h2>
              <div className="grid gap-3 md:grid-cols-2">
                <Card
                  id="overdue"
                  title="Overdue tasks"
                  tone="red"
                  total={a.overdue_tasks.total}
                  shown={a.overdue_tasks.items.length}
                >
                  {a.overdue_tasks.items.map((t) => (
                    <Item
                      key={t.id}
                      to={`${base}/projects/${t.project_id}/tasks?task=${t.id}`}
                      title={t.title}
                      tone="red"
                      meta={`${t.project_name} · ${t.assignee?.name ?? "Unassigned"} · ${dueText(-t.days_overdue)}`}
                    />
                  ))}
                </Card>
                <Card
                  id="ethics"
                  title="Ethics approvals"
                  tone={a.ethics.items.some((e) => e.expired) ? "red" : "amber"}
                  total={a.ethics.total}
                  shown={a.ethics.items.length}
                >
                  {a.ethics.items.map((e) => (
                    <Item
                      key={e.id}
                      to={`${base}/ethics/${e.id}`}
                      title={`${e.title} (${e.approval_number})`}
                      tone={e.expired ? "red" : "amber"}
                      meta={
                        e.expired
                          ? `Expired ${dueText(daysUntil(e.expiry_date), "ago")}`
                          : `Expires ${dueText(daysUntil(e.expiry_date))}`
                      }
                    />
                  ))}
                </Card>
                <Card
                  id="funding"
                  title="Funding ending"
                  tone={a.funding.items.some((f) => daysUntil(f.end_date) < 0) ? "red" : "amber"}
                  total={a.funding.total}
                  shown={a.funding.items.length}
                >
                  {a.funding.items.map((f) => (
                    <Item
                      key={f.id}
                      to={`${base}/projects/${f.project_id}/workflow/funding`}
                      title={`${f.funder} · ${f.project_name}`}
                      tone={daysUntil(f.end_date) < 0 ? "red" : "amber"}
                      meta={`${daysUntil(f.end_date) < 0 ? "Ended" : "Ends"} ${shortDate(f.end_date)} (${dueText(daysUntil(f.end_date), "ago")})`}
                    />
                  ))}
                </Card>
                <Card
                  id="deadlines"
                  title="Deadlines in 14 days"
                  tone="amber"
                  total={a.deadlines.total}
                  shown={a.deadlines.items.length}
                >
                  {a.deadlines.items.map((d) => (
                    <Item
                      key={d.id}
                      to={`${base}/projects/${d.project_id}/overview`}
                      title={d.title}
                      tone={daysUntil(d.due_date) < 0 ? "red" : "amber"}
                      badge={priorityBadge(d.priority)}
                      meta={`${d.project_name} · ${shortDate(d.due_date)} (${daysUntil(d.due_date) < 0 ? dueText(daysUntil(d.due_date), "late") : dueText(daysUntil(d.due_date))})`}
                    />
                  ))}
                </Card>
                <Card
                  id="stalled"
                  title="Stalled projects"
                  tone="amber"
                  total={a.stalled.total}
                  shown={a.stalled.items.length}
                >
                  {a.stalled.items.map((p) => (
                    <Item
                      key={p.project_id}
                      to={`${base}/projects/${p.project_id}/overview`}
                      title={p.project_name}
                      tone="amber"
                      meta={`No activity for ${plural(p.days_idle, "day")}`}
                    />
                  ))}
                </Card>
                <Card
                  id="unassigned"
                  title="Tasks that need an owner"
                  tone="amber"
                  total={a.unassigned.total}
                  shown={a.unassigned.items.length}
                >
                  {a.unassigned.items.map((t) => (
                    <Item
                      key={t.id}
                      to={`${base}/projects/${t.project_id}/tasks?task=${t.id}`}
                      title={t.title}
                      tone="amber"
                      meta={`${t.project_name}${t.due_date ? ` · due ${shortDate(t.due_date)}` : ""}`}
                    />
                  ))}
                </Card>
                <Card
                  id="integrations"
                  title="Integrations to fix"
                  tone="red"
                  total={a.integrations.total}
                  shown={a.integrations.items.length}
                >
                  {a.integrations.items.map((i) => (
                    <Item
                      key={i.id}
                      to={`${base}/settings/integrations`}
                      title={i.provider.replace(/_/g, " ")}
                      tone="red"
                      meta={`${i.user.name} · ${i.status === "expired" ? "needs to reconnect" : "has an error"}`}
                    />
                  ))}
                </Card>
                {a.dmp && (
                  <Card
                    id="dmp"
                    title="No approved data management plan"
                    tone="amber"
                    total={a.dmp.total}
                    shown={a.dmp.items.length}
                  >
                    {a.dmp.items.map((p) => (
                      <Item
                        key={p.project_id}
                        to={`${base}/projects/${p.project_id}/workflow/data`}
                        title={p.project_name}
                        tone="amber"
                        meta={p.dmp_status === "none" ? "No plan yet" : `Plan is ${p.dmp_status}`}
                      />
                    ))}
                  </Card>
                )}
                {/* D174: fed by GET L/training/expiring/ (training app). Hidden if that call fails. */}
                {tr && (
                  <Card
                    id="training"
                    title="Training expiring"
                    tone={tr.expired_count > 0 ? "red" : "amber"}
                    total={tr.count}
                    shown={tr.items.length}
                  >
                    {tr.items.slice(0, 20).map((i) => (
                      <Item
                        key={`${i.user.id}-${i.requirement.id}`}
                        to={`${base}/training`}
                        title={`${i.requirement.name} · ${i.user.display_name || i.user.email}`}
                        tone={i.status === "expired" ? "red" : "amber"}
                        meta={
                          i.status === "expired"
                            ? `Expired ${dueText(i.days_left, "ago")}`
                            : `Expires ${dueText(i.days_left)}`
                        }
                      />
                    ))}
                  </Card>
                )}
              </div>
            </section>
          )}

          <section aria-labelledby="projects" className="grid gap-3">
            <h2 id="projects" className="text-base font-semibold">
              Projects
            </h2>
            <ProjectTable
              labId={labId}
              projects={data.projects}
              seesFunding={lab?.my_permissions.includes("access_funding") ?? false}
            />
          </section>

          <section aria-labelledby="people" className="grid gap-3">
            <div>
              <h2 id="people" className="text-base font-semibold">
                People
              </h2>
              <p className="text-xs text-muted-foreground">
                Task counts only, from tasks assigned to each person. Done in 30 days counts tasks
                last marked done in that time.
              </p>
            </div>
            <PeopleTable people={data.people} />
          </section>

          <ContributionGraph labId={labId} people={data.people} />
        </div>
      )}
    </>
  );
}
