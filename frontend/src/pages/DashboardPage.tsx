import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  ChevronRight,
  ChevronsUpDown,
  CircleAlert,
  FolderKanban,
  type LucideIcon,
} from "lucide-react";
import { createContext, Fragment, useContext, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { ContributionGraph } from "@/components/dashboard/ContributionGraph";
import { GettingStarted } from "@/components/dashboard/GettingStarted";
import { MorningDigest } from "@/components/dashboard/MorningDigest";
import { ParticipantCards } from "@/components/dashboard/ParticipantCards";
import { Today } from "@/components/dashboard/Today";
import { FormError } from "@/components/shared/FormError";
import { Hint } from "@/components/shared/Hint";
import {
  CustomizeHome,
  ProjectRowActions,
  useHomeLayout,
  useSnooze,
  type HomeSection,
} from "@/components/dashboard/HomeParts";
import { Disclosure } from "@/components/shared/Disclosure";
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
import { NextMeeting } from "@/components/dashboard/NextMeeting";
import { useDashboard, useLowStock, type DashPerson, type DashProject } from "@/hooks/dashboard";
import { useMyTasks } from "@/hooks/projects";
import { useCompliance } from "@/hooks/training";
import { useLab, useMe } from "@/hooks/workspace";
import type { InventoryItem } from "@/lib/api-types";
import { digestOf } from "@/components/dashboard/MorningDigest";
import { localDateISO } from "@/lib/format";
import { roleLabel } from "@/lib/api-types";
import { daysUntil } from "@/lib/ethics";
import {
  dueText,
  daysFromToday,
  HEALTH_LABEL,
  HEALTH_RULE,
  overdueTotal,
  shortDate,
  sortProjects,
  type SortKey,
} from "@/lib/dashboard";
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
const TONE_ICON: Record<Tone, LucideIcon> = {
  red: CircleAlert,
  amber: AlertTriangle,
  green: CheckCircle2,
};

const SnoozeCtx = createContext<ReturnType<typeof useSnooze> | null>(null);

/** One kind of problem. A kind with nothing wrong is not shown at all. It says how many, names one
 * plain action ("Fix"), and can rest for a week when the gap is known. */
function Card({
  id,
  title,
  tone,
  total,
  shown,
  verb,
  hint,
  defaultOpen,
  children,
}: {
  id: string;
  title: string;
  tone: "red" | "amber";
  /** Show the items without a click. */
  defaultOpen?: boolean;
  total: number;
  shown: number;
  /** The one thing to do about it, and where. */
  verb?: { label: string; to: string };
  /** The rule that puts something here. */
  hint?: string;
  children: ReactNode;
}) {
  const snooze = useContext(SnoozeCtx);
  if (total === 0 || snooze?.resting(id)) return null;
  const Icon = TONE_ICON[tone];
  // Folded to one quiet line: the kind of problem and how many. The detail opens on demand.
  return (
    <details
      id={id}
      open={defaultOpen || undefined}
      role="region"
      aria-labelledby={`${id}-title`}
      className="group/card rounded-lg border bg-card/60 px-4 py-3 open:bg-card"
    >
      <summary
        id={`${id}-title`}
        className="flex cursor-pointer list-none items-center gap-2 text-sm font-medium [&::-webkit-details-marker]:hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        <Icon className={cn("size-4 shrink-0", TONE_TEXT[tone])} aria-hidden />
        <span className="min-w-0">{title}</span>
        {hint && <Hint text={hint} label="Why is this here?" />}
        <span className="ml-auto tabular-nums text-muted-foreground">{total}</span>
        {verb && (
          <Link
            to={verb.to}
            onClick={(e) => e.stopPropagation()}
            className="shrink-0 rounded-md bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary hover:bg-primary/20 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            {verb.label} →
          </Link>
        )}
        <ChevronRight
          aria-hidden
          className="size-4 shrink-0 text-muted-foreground transition-transform group-open/card:rotate-90"
        />
      </summary>
      <ul className="mt-3 grid gap-2 text-sm">{children}</ul>
      <div className="mt-3 flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          {total > shown ? `Showing ${shown} of ${total}.` : ""}
        </p>
        {snooze && (
          <Button
            variant="ghost"
            size="sm"
            title="Hide this for a week. It comes back by itself."
            onClick={() => snooze.snooze(id)}
          >
            Snooze for a week
          </Button>
        )}
      </div>
    </details>
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
        <p className={cn("text-[13px]", TONE_TEXT[tone])}>{meta}</p>
      </div>
      {badge}
    </li>
  );
}

/** Stock at or below the alert level set on the item. */
function LowStockCard({ base, items }: { base: string; items: InventoryItem[] }) {
  return (
    <Card
      id="lowstock"
      verb={{ label: "Open", to: `${base}/inventory` }}
      hint="Items at or below the alert level set on the item."
      title="Low stock"
      tone="amber"
      total={items.length}
      shown={items.length}
    >
      {items.map((i) => (
        <Item
          key={i.id}
          to={`${base}/inventory`}
          title={i.name}
          tone="amber"
          meta={`${i.quantity} ${i.unit} left (alert at ${i.low_stock_at})`}
        />
      ))}
    </Card>
  );
}

const priorityBadge = (p: string) => (
  <Badge variant={p === "high" ? "destructive" : p === "medium" ? "warning" : "success"}>{p}</Badge>
);

/** Nothing to report reads as a dash, so the real numbers stand out. */
const dash = (n: number) => (n === 0 ? <span className="text-muted-foreground">–</span> : n);

/** A due date, in red with "4 days overdue" once it has passed. */
function DeadlineDate({ date }: { date: string }) {
  const days = daysFromToday(date);
  return days < 0 ? (
    <span className="text-xs font-medium text-danger-text">
      {shortDate(date)} · {dueText(days)}
    </span>
  ) : (
    <span className="text-xs text-muted-foreground">{shortDate(date)}</span>
  );
}

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

/** `more` columns stay folded away until "All columns" is chosen. */
const COLUMNS: { key: SortKey; header: string; right?: boolean; more?: boolean }[] = [
  { key: "name", header: "Project" },
  { key: "status", header: "Status", more: true },
  { key: "health", header: "Health" },
  { key: "open", header: "Open", right: true },
  { key: "overdue", header: "Overdue", right: true },
  { key: "in_progress", header: "In progress", right: true, more: true },
  { key: "deadline", header: "Next deadline" },
  { key: "edited", header: "Last edited", more: true },
  { key: "funding", header: "Funding ends", more: true },
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
  const [filters, setFilters] = useState({ status: "", health: "", lead: "" });
  const [allColumns, setAllColumns] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [showDone, setShowDone] = useState(false);
  const navigate = useNavigate();
  const finished = projects.filter((p) => p.status === "completed" || p.status === "archived");
  // Finished projects are out of the table until asked for, and then they say what they are.
  const col = (key: SortKey) =>
    allColumns || (key === "status" && showDone) || !COLUMNS.find((c) => c.key === key)?.more;
  const leads = useMemo(
    () => [...new Set(projects.flatMap((p) => p.leads.map((l) => l.name)))].sort(),
    [projects],
  );
  const statuses = useMemo(() => [...new Set(projects.map((p) => p.status))].sort(), [projects]);
  const rows = useMemo(
    () =>
      sortProjects(
        projects.filter(
          (p) =>
            (showDone || (p.status !== "completed" && p.status !== "archived")) &&
            (!filters.status || p.status === filters.status) &&
            (!filters.health || p.health === filters.health) &&
            (!filters.lead || p.leads.some((l) => l.name === filters.lead)),
        ),
        sort.key,
        sort.dir,
      ),
    [projects, sort, filters, showDone],
  );
  const filtering = !!(filters.status || filters.health || filters.lead);
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

  const selectClass =
    "h-8 rounded-md border bg-background px-2 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none";
  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          aria-expanded={showFilters || filtering}
          onClick={() => setShowFilters((v) => !v)}
        >
          Filter
        </Button>
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={allColumns}
          onClick={() => setAllColumns((v) => !v)}
        >
          All columns
        </Button>
        {finished.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            aria-pressed={showDone}
            onClick={() => setShowDone((v) => !v)}
          >
            {showDone ? "Hide" : "Show"} completed and archived ({finished.length})
          </Button>
        )}
        <span className="ml-auto text-xs text-muted-foreground" aria-live="polite">
          {rows.length} of {projects.length - (showDone ? 0 : finished.length)}
        </span>
      </div>
      <div
        role="group"
        aria-label="Filter projects"
        hidden={!(showFilters || filtering)}
        className="flex flex-wrap items-center gap-2"
      >
        <select
          aria-label="Status"
          className={cn(selectClass, "capitalize")}
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
        >
          <option value="">All statuses</option>
          {statuses.map((s) => (
            <option key={s} value={s}>
              Status: {s.replace(/_/g, " ")}
            </option>
          ))}
        </select>
        <select
          aria-label="Health"
          className={selectClass}
          value={filters.health}
          onChange={(e) => setFilters({ ...filters, health: e.target.value })}
        >
          <option value="">Any health</option>
          {(Object.keys(HEALTH_LABEL) as (keyof typeof HEALTH_LABEL)[]).map((h) => (
            <option key={h} value={h}>
              Health: {HEALTH_LABEL[h]}
            </option>
          ))}
        </select>
        <select
          aria-label="Project lead"
          className={selectClass}
          value={filters.lead}
          onChange={(e) => setFilters({ ...filters, lead: e.target.value })}
        >
          <option value="">Any lead</option>
          {leads.map((l) => (
            <option key={l} value={l}>
              Lead: {l}
            </option>
          ))}
        </select>
        {filtering && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setFilters({ status: "", health: "", lead: "" })}
          >
            Clear filters
          </Button>
        )}
      </div>
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              {COLUMNS.filter((c) => (seesFunding || c.key !== "funding") && col(c.key)).map(
                (c) => {
                  const active = sort.key === c.key;
                  return (
                    <TableHead
                      key={c.key}
                      aria-sort={
                        active ? (sort.dir === "asc" ? "ascending" : "descending") : "none"
                      }
                      className={c.right ? "text-right" : undefined}
                    >
                      <button
                        type="button"
                        onClick={() => toggle(c.key)}
                        className="inline-flex items-center gap-1 rounded-sm font-medium hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {c.header}
                        {active ? (
                          sort.dir === "asc" ? (
                            <ArrowUp className="size-3.5 text-primary" aria-hidden />
                          ) : (
                            <ArrowDown className="size-3.5 text-primary" aria-hidden />
                          )
                        ) : (
                          <ChevronsUpDown className="size-3 opacity-40" aria-hidden />
                        )}
                      </button>
                      {c.key === "health" && (
                        <span className="ml-1 align-middle">
                          <Hint
                            text={`${HEALTH_RULE.red} ${HEALTH_RULE.amber} ${HEALTH_RULE.green}`}
                            label="How is health decided?"
                          />
                        </span>
                      )}
                    </TableHead>
                  );
                },
              )}
              <TableHead className="w-0">
                <span className="sr-only">Quick actions</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((p) => (
              <TableRow
                key={p.id}
                className="cursor-pointer"
                onClick={(e) => {
                  // the whole row opens the project, except where a link or a button took the click
                  if ((e.target as HTMLElement).closest("a,button,[role=menuitem]")) return;
                  void navigate(`/labs/${labId}/projects/${p.id}`);
                }}
              >
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
                {col("status") && (
                  <TableCell>
                    <StatusBadge status={p.status} />
                  </TableCell>
                )}
                <TableCell>
                  <Health p={p} />
                </TableCell>
                <TableCell className="text-right tabular-nums">{dash(p.open_tasks)}</TableCell>
                <TableCell
                  className={cn(
                    "text-right tabular-nums",
                    overdueTotal(p) > 0 && "font-semibold text-danger-text",
                  )}
                  title={
                    overdueTotal(p)
                      ? `${p.overdue_tasks} overdue tasks, ${p.overdue_deadlines} overdue deadlines`
                      : undefined
                  }
                >
                  {dash(overdueTotal(p))}
                </TableCell>
                {col("in_progress") && (
                  <TableCell className="text-right tabular-nums">
                    {dash(p.in_progress_tasks)}
                  </TableCell>
                )}
                <TableCell className="min-w-40">
                  {p.next_deadline ? (
                    <>
                      <span className="flex items-center gap-1.5">
                        {p.next_deadline.title}
                        {priorityBadge(p.next_deadline.priority)}
                      </span>
                      <DeadlineDate date={p.next_deadline.due_date} />
                    </>
                  ) : (
                    <span className="text-muted-foreground">–</span>
                  )}
                </TableCell>
                {col("edited") && (
                  <TableCell className="min-w-32">
                    {p.last_activity_at ? (
                      <>
                        <RelativeTime value={p.last_activity_at} />
                        {p.last_activity_by && (
                          <p className="text-xs text-muted-foreground">
                            by {p.last_activity_by.name}
                          </p>
                        )}
                      </>
                    ) : (
                      <span className="text-muted-foreground">–</span>
                    )}
                  </TableCell>
                )}
                {seesFunding && col("funding") && (
                  <TableCell className="min-w-28">
                    {p.funding_end_date ? (
                      <>
                        {shortDate(p.funding_end_date)}
                        <p className="text-xs text-muted-foreground capitalize">
                          {p.funding_status}
                        </p>
                      </>
                    ) : (
                      <span className="text-muted-foreground">–</span>
                    )}
                  </TableCell>
                )}
                <TableCell className="text-right">
                  <ProjectRowActions labId={labId} project={p} />
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow className="hover:bg-transparent">
                <TableCell
                  colSpan={COLUMNS.length}
                  className="py-6 text-center text-muted-foreground"
                >
                  No projects match these filters.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
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

/** What is yours to do now: your own overdue tasks and the ones due today, before any status. */
function YourPlate({ labId }: { labId: string }) {
  const { data: tasks } = useMyTasks(labId);
  const today = localDateISO();
  const d = digestOf(tasks ?? [], today);
  const now = [...d.overdue, ...d.today];
  if (now.length === 0) return null;
  return (
    <section aria-labelledby="your-plate" className="grid gap-2 rounded-lg border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 id="your-plate" className="text-base font-medium">
          On your plate
          <span className="ml-2 text-sm font-normal text-muted-foreground">
            {[
              d.overdue.length && `${d.overdue.length} overdue`,
              d.today.length && `${d.today.length} due today`,
            ]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </h2>
        <Link
          to={`/labs/${labId}/my-work`}
          className="text-sm text-primary underline-offset-2 hover:underline"
        >
          Open My work →
        </Link>
      </div>
      <ul className="grid gap-1 text-sm">
        {now.slice(0, 5).map((t) => (
          <li key={t.id} className="flex items-baseline justify-between gap-3">
            <Link
              to={`/labs/${labId}/projects/${t.project}/tasks?task=${t.id}`}
              className="min-w-0 truncate font-medium underline-offset-2 hover:underline"
            >
              {t.title}
            </Link>
            <span
              className={cn(
                "shrink-0 text-xs",
                t.due_date && t.due_date < today
                  ? "font-medium text-danger-text"
                  : "text-muted-foreground",
              )}
            >
              {t.project_name} ·{" "}
              {t.due_date && t.due_date < today ? dueText(daysFromToday(t.due_date)) : "due today"}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Home, for everyone: PIs and lab admins see how the lab stands (D171), others their own tasks. */
export function DashboardPage() {
  const { labId = "" } = useParams();
  const { data: lab, error: labError } = useLab(labId);
  const allowed = lab?.my_permissions.includes("manage_lab") ?? false;
  const { data, error, isLoading } = useDashboard(labId, allowed);
  const training = useCompliance(labId, allowed);
  const me = useMe().data;
  const [mine, setMine] = useState(false);
  const lowOn = !!lab?.inventory_enabled && !!lab.my_permissions.includes("manage_inventory");
  const lowStock = useLowStock(labId, lowOn);
  const base = `/labs/${labId}`;
  const layout = useHomeLayout(labId);
  const snooze = useSnooze(labId);

  const failure = labError ?? error;
  if (failure) return <FormError message={formErrors(failure, []).form} />;

  const header = (
    <>
      <PageHeader
        title="Home"
        description={lab && `${lab.name} · You are ${roleLabel(lab.my_role ?? "")}`}
        actions={
          lab ? (
            <>
              <MorningDigest labId={labId} />
              <CustomizeHome layout={layout} />
            </>
          ) : undefined
        }
      />
      {lab && <NextMeeting labId={labId} />}
      {lab && !allowed && <Today labId={labId} />}
    </>
  );
  const extras = (
    <div className="mt-6 grid gap-4">
      <GettingStarted labId={labId} />
      {lab && <ParticipantCards labId={labId} />}
      {layout.shown.includes("recent") && <Recents hide={["project"]} />}
    </div>
  );
  if (lab && !allowed)
    return (
      <>
        {header}
        {lowStock.data && lowStock.data.length > 0 && (
          <section aria-labelledby="attention" className="mb-6 grid gap-3">
            <h2 id="attention" className="text-base font-medium">
              Needs attention
            </h2>
            <LowStockCard base={base} items={lowStock.data} />
          </section>
        )}
        <section aria-labelledby="my-tasks" className="grid gap-3">
          <h2 id="my-tasks" className="text-base font-medium">
            My tasks
          </h2>
          <MyTasksList labId={labId} />
        </section>
        {extras}
      </>
    );

  // Training: everything that is expired, expiring or has no record (what the matrix shows).
  const trainingItems = (training.data?.members ?? []).flatMap((m) =>
    training.data!.requirements.flatMap((r) => {
      const cell = m.cells[r.id];
      return cell && ["expired", "expiring", "missing"].includes(cell.status)
        ? [{ user: m.user, requirement: r, cell }]
        : [];
    }),
  );
  const rank = { expired: 0, missing: 1, expiring: 2 } as Record<string, number>;
  trainingItems.sort((x, y) => rank[x.cell.status]! - rank[y.cell.status]!);

  // "Mine only": my tasks, my integrations and training, and the projects I lead.
  const raw = data?.attention;
  const myId = me?.id;
  const led = new Set(
    (data?.projects ?? []).filter((p) => p.leads.some((l) => l.id === myId)).map((p) => p.id),
  );
  const pick = <T,>(g: { total: number; items: T[] }, keep: (i: T) => boolean) => {
    if (!mine) return g;
    const items = g.items.filter(keep);
    return { total: items.length, items };
  };
  const inLed = (i: { project_id: string }) => led.has(i.project_id);
  const a = raw && {
    overdue_tasks: pick(raw.overdue_tasks, (t) => t.assignee?.id === myId),
    ethics: pick(raw.ethics, () => false), // approvals belong to no one in particular
    funding: pick(raw.funding, inLed),
    deadlines: pick(raw.deadlines, inLed),
    stalled: pick(raw.stalled, inLed),
    unassigned: pick(raw.unassigned, inLed),
    integrations: pick(raw.integrations, (i) => i.user.id === myId),
    dmp: raw.dmp && pick(raw.dmp, inLed),
  };
  const trItems = mine ? trainingItems.filter((i) => i.user.id === myId) : trainingItems;
  const lowItems = (lowStock.data ?? []).filter((i) => !mine || i.owner?.id === myId);
  const tr = training.data && { count: trItems.length };
  const problems =
    (a &&
      [
        a.overdue_tasks,
        a.ethics,
        a.funding,
        a.deadlines,
        a.stalled,
        a.unassigned,
        a.integrations,
        a.dmp ?? { total: 0 },
      ].some((group) => group.total > 0)) ||
    lowItems.length > 0;

  const homeSection = (id: HomeSection) =>
    id === "recent" ? (
      <Recents hide={["project"]} />
    ) : id === "people" && data ? (
      <Disclosure title="People" hint={`${data.people.length} in the lab`}>
        <p className="mb-3 text-xs text-muted-foreground">
          Task counts only, from tasks assigned to each person. Done in 30 days counts tasks last
          marked done in that time.
        </p>
        <PeopleTable people={data.people} />
      </Disclosure>
    ) : id === "activity" && data ? (
      <Disclosure title="Activity" hint="Who has been working, by day" defaultOpen>
        <ContributionGraph labId={labId} people={data.people} />
      </Disclosure>
    ) : null;

  return (
    <>
      {header}
      {isLoading || training.isLoading || !data || !a ? (
        <DashboardSkeleton />
      ) : (
        <SnoozeCtx.Provider value={snooze}>
          <div className="grid gap-6">
            <GettingStarted labId={labId} />
            <YourPlate labId={labId} />
            {!problems && !tr?.count && !mine ? (
              <p
                role="status"
                className="flex items-center gap-2 text-sm font-medium text-success-text"
              >
                <CheckCircle2 className="size-4" aria-hidden />
                All clear. Nothing needs attention right now.
              </p>
            ) : (
              <section aria-labelledby="attention" className="grid gap-3">
                <div className="flex items-center justify-between gap-2">
                  <h2 id="attention" className="text-base font-medium">
                    Needs attention
                  </h2>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-pressed={mine}
                    title="Show only what is yours: your tasks, your projects, your training"
                    onClick={() => setMine((v) => !v)}
                  >
                    Mine only
                  </Button>
                </div>
                {!problems && !tr?.count && (
                  <p role="status" className="text-sm text-muted-foreground">
                    Nothing of yours needs attention.
                  </p>
                )}
                <div className="grid items-start gap-2 md:grid-cols-2">
                  <Card
                    id="overdue"
                    defaultOpen
                    hint="Tasks whose due date has passed and are not done."
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
                    verb={{ label: "Renew", to: `${base}/ethics` }}
                    hint="Approvals that have expired or expire within 60 days."
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
                    verb={{
                      label: "Review",
                      to: `${base}/projects/${a.funding.items[0]?.project_id}/workflow/funding`,
                    }}
                    hint="Active funding that ends within 90 days, or has already ended."
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
                    verb={{
                      label: "Open",
                      to: `${base}/projects/${a.deadlines.items[0]?.project_id}/overview`,
                    }}
                    hint="Deadlines that are late or fall within 14 days."
                    title="Deadlines overdue or due in 14 days"
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
                    verb={{
                      label: "Check in",
                      to: `${base}/projects/${a.stalled.items[0]?.project_id}/overview`,
                    }}
                    hint="Planning or active projects with no activity for 30 days."
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
                    verb={{
                      label: "Assign",
                      to: `${base}/projects/${a.unassigned.items[0]?.project_id}/tasks`,
                    }}
                    hint="Open tasks with nobody assigned."
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
                    verb={{ label: "Reconnect", to: `${base}/settings/integrations` }}
                    hint="Connected accounts that have expired or are reporting an error."
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
                      verb={{
                        label: "Fix",
                        to: `${base}/projects/${a.dmp?.items[0]?.project_id}/workflow/data`,
                      }}
                      hint="Planning or active projects older than 14 days (or holding data) whose data management plan is not approved."
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
                  {lowItems.length > 0 && <LowStockCard base={base} items={lowItems} />}
                  {/* Everyone the matrix flags: expired, expiring or no record (D174). */}
                  {tr && (
                    <Card
                      id="training"
                      verb={{ label: "Review", to: `${base}/training` }}
                      hint="Required training that has expired, expires within 60 days, or has no record yet."
                      title="Training needs attention (expired, expiring or missing)"
                      tone={trItems.some((i) => i.cell.status !== "expiring") ? "red" : "amber"}
                      total={trItems.length}
                      shown={Math.min(trItems.length, 20)}
                    >
                      {trItems.slice(0, 20).map((i) => (
                        <Item
                          key={`${i.user.id}-${i.requirement.id}`}
                          to={`${base}/training`}
                          title={`${i.requirement.name} · ${i.user.display_name || i.user.email}`}
                          tone={i.cell.status === "expiring" ? "amber" : "red"}
                          meta={
                            i.cell.status === "missing"
                              ? "No record yet"
                              : i.cell.status === "expired"
                                ? `Expired ${dueText(i.cell.days_left ?? 0, "ago")}`
                                : `Expires ${dueText(i.cell.days_left ?? 0)}`
                          }
                        />
                      ))}
                    </Card>
                  )}
                </div>
              </section>
            )}
            {snooze.restingIds.length > 0 && (
              <p className="-mt-3 text-xs text-muted-foreground">
                {plural(snooze.restingIds.length, "kind of problem")} snoozed for now.{" "}
                <button
                  type="button"
                  onClick={snooze.wakeAll}
                  className="underline underline-offset-2 hover:text-foreground"
                >
                  Show them again
                </button>
              </p>
            )}
            {lab && <ParticipantCards labId={labId} />}
            <section aria-labelledby="projects" className="grid gap-3">
              <h2 id="projects" className="text-base font-medium">
                Projects
              </h2>
              <ProjectTable
                labId={labId}
                projects={data.projects}
                seesFunding={
                  (lab?.my_permissions.includes("access_funding") ?? false) &&
                  data.projects.some((p) => p.funding_end_date)
                }
              />
            </section>

            {layout.shown.map((id) => (
              <Fragment key={id}>{homeSection(id)}</Fragment>
            ))}
          </div>
        </SnoozeCtx.Provider>
      )}
    </>
  );
}
