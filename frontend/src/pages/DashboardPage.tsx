import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  CircleAlert,
  ClipboardList,
  FolderKanban,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Link, Navigate, useParams } from "react-router";
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
import { dueText, HEALTH_LABEL, shortDate, sortProjects, type SortKey } from "@/lib/dashboard";
import { formErrors } from "@/lib/forms";
import { plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import { LabHomePage } from "@/pages/LabHomePage";

/** `/labs/:id` for pi and lab_admin lands on the dashboard; everyone else keeps the project list (D171). */
export function LabIndexPage() {
  const { labId = "" } = useParams();
  const { data: lab } = useLab(labId);
  if (lab?.my_permissions.includes("manage_lab")) return <Navigate to="dashboard" replace />;
  return <LabHomePage />;
}

type Tone = "red" | "amber" | "green" | "neutral";
// Colour is never the only signal: every tone also has an icon and a word (see Tile and Card).
const TONE_TEXT: Record<Tone, string> = {
  red: "text-danger-text",
  amber: "text-warning-text",
  green: "text-success-text",
  neutral: "text-foreground",
};
const TONE_EDGE: Record<Tone, string> = {
  red: "border-danger/50 bg-danger/5",
  amber: "border-warning/60 bg-warning/5",
  green: "border-success/40 bg-success/5",
  neutral: "bg-card",
};
const TONE_ICON: Record<Tone, LucideIcon> = {
  red: CircleAlert,
  amber: AlertTriangle,
  green: CheckCircle2,
  neutral: ClipboardList,
};
const TONE_WORD: Record<Tone, string> = {
  red: "Act now",
  amber: "Due soon",
  green: "All clear",
  neutral: "",
};

function Tile({
  label,
  value,
  tone,
  href,
}: {
  label: string;
  value: number;
  tone: Tone;
  href?: string;
}) {
  const Icon = TONE_ICON[tone];
  const body = (
    <div className={cn("grid gap-1 rounded-lg border p-4", TONE_EDGE[tone])}>
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <span className={cn("text-3xl font-semibold tabular-nums", TONE_TEXT[tone])}>{value}</span>
      {tone !== "neutral" && (
        <span className={cn("flex items-center gap-1 text-xs font-medium", TONE_TEXT[tone])}>
          <Icon className="size-3.5" aria-hidden />
          {TONE_WORD[tone]}
        </span>
      )}
    </div>
  );
  return href ? (
    <a
      href={href}
      className="rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {body}
    </a>
  ) : (
    body
  );
}

function Card({
  id,
  title,
  tone,
  total,
  shown,
  empty,
  children,
}: {
  id: string;
  title: string;
  tone: Tone;
  total: number;
  shown: number;
  empty: string;
  children: ReactNode;
}) {
  const state: Tone = total === 0 ? "green" : tone;
  const Icon = TONE_ICON[state];
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className={cn("scroll-mt-4 rounded-lg border p-4", TONE_EDGE[state])}
    >
      <h3
        id={`${id}-title`}
        className={cn("flex items-center gap-2 text-sm font-semibold", TONE_TEXT[state])}
      >
        <Icon className="size-4" aria-hidden />
        {title}
        <span className="ml-auto tabular-nums">{total}</span>
      </h3>
      {total === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">{empty}</p>
      ) : (
        <>
          <ul className="mt-3 grid gap-2 text-sm">{children}</ul>
          {total > shown && (
            <p className="mt-3 text-xs text-muted-foreground">
              Showing {shown} of {total}.
            </p>
          )}
        </>
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

function ProjectTable({ labId, projects }: { labId: string; projects: DashProject[] }) {
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
            {COLUMNS.map((c) => {
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
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-36" />
        ))}
      </div>
      <Skeleton className="h-64" />
    </div>
  );
}

export function DashboardPage() {
  const { labId = "" } = useParams();
  const { data: lab, error: labError } = useLab(labId);
  const allowed = lab?.my_permissions.includes("manage_lab") ?? false;
  const { data, error, isLoading } = useDashboard(labId, allowed);
  const training = useTrainingExpiring(labId, allowed);
  const base = `/labs/${labId}`;

  const failure = labError ?? error;
  if (failure) return <FormError message={formErrors(failure, []).form} />;
  if (lab && !allowed)
    return (
      <EmptyState
        title="The dashboard is for PIs and lab admins"
        description="You can see your own projects and tasks from the sidebar."
      />
    );

  const a = data?.attention;
  const s = data?.summary;
  const tr = training.data;
  const tone = (n: number, t: Tone): Tone => (n > 0 ? t : "green");

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Where the lab stands: what is late, what is due soon, and where nothing has moved."
        actions={
          <Button asChild variant="outline">
            <Link to={`${base}/projects`}>All projects</Link>
          </Button>
        }
      />
      <Recents />
      {isLoading || !data || !a || !s ? (
        <DashboardSkeleton />
      ) : (
        <div className="grid gap-8">
          <section aria-label="Summary" className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Tile label="Active projects" value={s.active_projects} tone="neutral" />
            <Tile label="Open tasks" value={s.open_tasks} tone="neutral" />
            <Tile
              label="Overdue tasks"
              value={s.overdue_tasks}
              tone={tone(s.overdue_tasks, "red")}
              href="#overdue"
            />
            <Tile
              label="Deadlines in 14 days"
              value={s.deadlines_soon}
              tone={tone(s.deadlines_soon, "amber")}
              href="#deadlines"
            />
            <Tile
              label="Ethics to renew"
              value={s.ethics_attention}
              tone={tone(
                s.ethics_attention,
                a.ethics.items.some((e) => e.expired) ? "red" : "amber",
              )}
              href="#ethics"
            />
            <Tile
              label="Funding ending in 90 days"
              value={s.funding_ending}
              tone={tone(
                s.funding_ending,
                a.funding.items.some((f) => f.days_left < 0) ? "red" : "amber",
              )}
              href="#funding"
            />
            <Tile
              label="Stalled projects"
              value={s.stalled_projects}
              tone={tone(s.stalled_projects, "amber")}
              href="#stalled"
            />
            <Tile
              label="Need an owner"
              value={s.unassigned_tasks}
              tone={tone(s.unassigned_tasks, "amber")}
              href="#unassigned"
            />
          </section>

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
                empty="Nothing is overdue."
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
                empty="No approvals expire in the next 60 days."
              >
                {a.ethics.items.map((e) => (
                  <Item
                    key={e.id}
                    to={`${base}/ethics/${e.id}`}
                    title={`${e.title} (${e.approval_number})`}
                    tone={e.expired ? "red" : "amber"}
                    meta={
                      e.expired
                        ? `Expired ${dueText(e.days_left, "ago")}`
                        : `Expires ${dueText(e.days_left)}`
                    }
                  />
                ))}
              </Card>
              <Card
                id="funding"
                title="Funding ending"
                tone={a.funding.items.some((f) => f.days_left < 0) ? "red" : "amber"}
                total={a.funding.total}
                shown={a.funding.items.length}
                empty="No funding ends in the next 90 days."
              >
                {a.funding.items.map((f) => (
                  <Item
                    key={f.id}
                    to={`${base}/projects/${f.project_id}/workflow/funding`}
                    title={`${f.funder} · ${f.project_name}`}
                    tone={f.days_left < 0 ? "red" : "amber"}
                    meta={`${f.days_left < 0 ? "Ended" : "Ends"} ${shortDate(f.end_date)} (${dueText(f.days_left, "ago")})`}
                  />
                ))}
              </Card>
              <Card
                id="deadlines"
                title="Deadlines in 14 days"
                tone="amber"
                total={a.deadlines.total}
                shown={a.deadlines.items.length}
                empty="No deadlines in the next 14 days."
              >
                {a.deadlines.items.map((d) => (
                  <Item
                    key={d.id}
                    to={`${base}/projects/${d.project_id}/overview`}
                    title={d.title}
                    tone={d.days_left < 0 ? "red" : "amber"}
                    badge={priorityBadge(d.priority)}
                    meta={`${d.project_name} · ${shortDate(d.due_date)} (${d.days_left < 0 ? dueText(d.days_left, "late") : dueText(d.days_left)})`}
                  />
                ))}
              </Card>
              <Card
                id="stalled"
                title="Stalled projects"
                tone="amber"
                total={a.stalled.total}
                shown={a.stalled.items.length}
                empty="Every active project has been touched in the last 30 days."
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
                empty="No tasks were left without an owner after an access change."
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
                empty="Every connected service is working."
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
                  empty="Every planning or active project has an approved plan."
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
                  empty="No certifications expire in the next 60 days."
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

          <section aria-labelledby="projects" className="grid gap-3">
            <h2 id="projects" className="text-base font-semibold">
              Projects
            </h2>
            <ProjectTable labId={labId} projects={data.projects} />
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
        </div>
      )}
    </>
  );
}
