import {
  ChevronRight,
  MoreHorizontal,
  Plus,
  Search,
  SlidersHorizontal,
  Users,
  X,
  ArrowDownUp,
  ArrowDown,
  ArrowUp,
} from "lucide-react";
import { Fragment, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { toast } from "sonner";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { DEFAULT_VIEW, useViewPrefs, type RegistryView } from "@/hooks/viewPrefs";
import { CustomizePanel } from "@/pages/project/participants/CustomizePanel";
import {
  useArchivedParticipants,
  useLinkHealth,
  useReasons,
  useRegistry,
} from "@/hooks/participants";
import { usePatchTask } from "@/hooks/projects";
import { useMe, useMembers } from "@/hooks/workspace";
import { personName } from "@/lib/api-types";
import type {
  CellStatus,
  RegistryCell,
  RegistryColumn,
  RegistryParticipant,
} from "@/lib/api-types";
import {
  CODES_ONLY,
  completeness,
  isOverdue,
  REASON_KIND,
  STATUS,
  STATUSES,
  statusOf,
} from "@/lib/participants";
import { formErrors } from "@/lib/forms";
import { cn } from "@/lib/utils";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { CellPanel } from "@/pages/project/participants/CellPanel";
import {
  AddParticipantsDialog,
  ArchivedDialog,
  ColumnsDialog,
} from "@/pages/project/participants/Dialogs";
import { RulesDialog } from "@/pages/project/participants/RulesDialog";
import {
  ImportHistory,
  ImportWizard,
  LinkHealthDialog,
  MatchFilesDialog,
} from "@/pages/project/participants/ImportDialogs";
import { ParticipantDetail } from "@/pages/project/participants/ParticipantDetail";
import { TemplatePicker } from "@/pages/project/participants/TemplatePicker";
import { Suggestions, type Suggestion } from "@/pages/project/participants/Suggestions";
import { StatusChip } from "@/pages/project/participants/StatusChip";
import { NativeSelect } from "@/pages/project/workflow/parts";

const keyOf = (p: string, c: string) => `${p}:${c}`;

interface Target {
  p: RegistryParticipant;
  c: RegistryColumn;
}

const applies = (c: RegistryColumn, p: RegistryParticipant) =>
  c.applies_to_groups.length === 0 || c.applies_to_groups.includes(p.group);

/** Who has what: participants down the side, data columns across, one status chip per cell. */
export default function ParticipantRegistry({ labId, projectId, project }: ProjectTabProps) {
  const registry = useRegistry(labId, projectId);
  const reasons = useReasons(labId).data ?? [];
  const archived = useArchivedParticipants(labId, projectId).data ?? [];
  const canEdit = project.my_permissions.includes("edit_content");
  const canColumns = project.my_permissions.includes("edit_project");
  const participants = useMemo(
    () => registry.participants.data ?? [],
    [registry.participants.data],
  );
  const allColumns = useMemo(() => registry.columns.data ?? [], [registry.columns.data]);
  const {
    view,
    update: updateView,
    reset: resetView,
  } = useViewPrefs<RegistryView>("participants", projectId, DEFAULT_VIEW);
  const columns = useMemo(
    () => allColumns.filter((c) => !view.hidden.includes(c.id)),
    [allColumns, view.hidden],
  );
  const dismissedPrefs = useViewPrefs<{ ids: string[] }>("participants-dismissed", projectId, {
    ids: [],
  });
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [filtersOpen, setFiltersOpen] = useState(false);
  const cells = useMemo(() => registry.cells.data ?? [], [registry.cells.data]);

  // Sort by the code, the group, how much is done, or any data column; the choice is remembered.
  const sortPrefs = useViewPrefs<{ key: string; dir: "asc" | "desc" }>(
    "participants-sort",
    projectId,
    { key: "code", dir: "asc" },
  );
  const sort = sortPrefs.view;
  const [q, setQ] = useState("");
  const [group, setGroup] = useState("");
  const [params] = useSearchParams();
  const initialStatus = params.get("status") as CellStatus | null;
  const [status, setStatus] = useState<CellStatus | "">(
    initialStatus && STATUS[initialStatus] ? initialStatus : "",
  );
  const [overdueOnly, setOverdueOnly] = useState(params.get("overdue") === "1");
  const [ownerFilter, setOwnerFilter] = useState<"" | "me" | "others" | "none">(
    (["me", "others", "none"] as const).find((o) => o === params.get("owner")) ?? "",
  );
  const me = useMe().data;
  const members = useMembers(labId).data ?? [];
  const patchTask = usePatchTask(labId);
  const [taskMode, setTaskMode] = useState<"cell" | "participant" | "component">("cell");
  const [bulkOwner, setBulkOwner] = useState("");
  const [bulkDue, setBulkDue] = useState("");
  const [gapsOnly, setGapsOnly] = useState(false);
  const density = view.density;
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [anchor, setAnchor] = useState<{ r: number; c: number }>();
  const [open, setOpen] = useState<{ p: string; c: string; initial?: CellStatus }>();
  const [dialog, setDialog] = useState<
    | "add"
    | "columns"
    | "import"
    | "history"
    | "match"
    | "health"
    | "rules"
    | "customize"
    | "template"
    | "archived"
    | null
  >(null);
  const problemCount = useLinkHealth(labId, projectId).health.data?.counts;
  const [bulk, setBulk] = useState<{ status: CellStatus; reason: string }>({
    status: "complete",
    reason: "",
  });
  const grid = useRef<HTMLTableElement>(null);
  const [today] = useState(() => new Date().toLocaleDateString("en-CA"));

  const cellMap = useMemo(() => {
    const m = new Map<string, RegistryCell>();
    for (const c of cells) m.set(keyOf(c.participant, c.component), c);
    return m;
  }, [cells]);
  const cellOf = (p: RegistryParticipant, c: RegistryColumn) => cellMap.get(keyOf(p.id, c.id));

  const groups = [...new Set(participants.map((p) => p.group).filter(Boolean))].sort();
  const rows = participants.filter((p) => {
    if (q && !p.code.toLowerCase().includes(q.trim().toLowerCase())) return false;
    if (group && p.group !== group) return false;
    const mine = columns.filter((c) => applies(c, p)).map((c) => cellOf(p, c));
    if (status && !mine.some((c) => statusOf(c) === status)) return false;
    if (overdueOnly && !mine.some((c) => isOverdue(c, today))) return false;
    if (ownerFilter) {
      const open = mine.filter(
        (c) => !["complete", "not_applicable", "excluded"].includes(statusOf(c)),
      );
      const ok = open.some((c) =>
        ownerFilter === "me"
          ? !!me && c?.owner === me.id
          : ownerFilter === "none"
            ? !c?.owner
            : !!c?.owner && c.owner !== me?.id,
      );
      if (!ok) return false;
    }
    if (
      gapsOnly &&
      !mine.some((c) => ["not_started", "in_progress", "missing"].includes(statusOf(c)))
    )
      return false;
    return true;
  });

  const STATUS_RANK: CellStatus[] = [
    "missing",
    "not_started",
    "in_progress",
    "needs_review",
    "complete",
    "not_applicable",
    "excluded",
  ];
  const sortValue = (p: RegistryParticipant): number | string => {
    if (sort.key === "code") return p.code.toLowerCase();
    if (sort.key === "group") return (p.group ?? "").toLowerCase();
    if (sort.key === "done")
      return completeness(columns.filter((c) => applies(c, p)).map((c) => cellOf(p, c))).percent;
    const col = columns.find((c) => c.id === sort.key);
    if (!col || !applies(col, p)) return Number.MAX_SAFE_INTEGER;
    return STATUS_RANK.indexOf(statusOf(cellOf(p, col)));
  };
  rows.sort((a, b) => {
    const x = sortValue(a);
    const y = sortValue(b);
    const r =
      typeof x === "number" && typeof y === "number"
        ? x - y
        : String(x).localeCompare(String(y), undefined, { numeric: true });
    return sort.dir === "asc" ? r : -r;
  });
  const sortLabel =
    sort.key === "code"
      ? "Participant"
      : sort.key === "group"
        ? "Group"
        : sort.key === "done"
          ? "% done"
          : (columns.find((c) => c.id === sort.key)?.name ?? "Participant");

  const summary = useMemo(() => {
    const all = participants.flatMap((p) =>
      allColumns.filter((c) => applies(c, p)).map((c) => cellMap.get(keyOf(p.id, c.id))),
    );
    const count = (s: CellStatus) => all.filter((c) => statusOf(c) === s).length;
    return {
      ...completeness(all),
      missing: count("missing"),
      review: count("needs_review"),
      overdue: all.filter((c) => isOverdue(c, today)).length,
    };
  }, [participants, allColumns, cellMap, today]);

  const cellCounts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const c of cells) out[c.component] = (out[c.component] ?? 0) + 1;
    return out;
  }, [cells]);

  // ---- changes
  async function batch(targets: Target[], patch: (t: Target) => Parameters<typeof send>[2]) {
    for (let i = 0; i < targets.length; i += 8)
      await Promise.all(targets.slice(i, i + 8).map((t) => send(t.p, t.c, patch(t))));
  }
  const send = (
    p: RegistryParticipant,
    c: RegistryColumn,
    patch: {
      status?: CellStatus;
      reason?: string | null;
      owner?: string | null;
      due_date?: string | null;
    },
  ) => registry.setCell.mutateAsync({ participant: p.id, component: c.id, patch });

  async function setStatusFor(targets: Target[], next: CellStatus, reason?: string) {
    if (!canEdit || !targets.length) return;
    const before = targets.map((t) => {
      const cell = cellOf(t.p, t.c);
      return { t, status: statusOf(cell), reason: cell?.reason ?? null };
    });
    try {
      await batch(targets, () => ({ status: next, ...(reason ? { reason } : {}) }));
    } catch {
      toast.error("Some changes were not saved. They have been put back.");
      return;
    }
    const openTasks = new Map<string, string>();
    if (next === "complete")
      for (const t of targets)
        for (const task of cellOf(t.p, t.c)?.tasks ?? [])
          if (task.status !== "done") openTasks.set(task.id, task.title);
    if (openTasks.size)
      toast(
        openTasks.size === 1
          ? `There is a task for this: ${[...openTasks.values()][0]}`
          : `${openTasks.size} tasks were made for these cells`,
        {
          action: {
            label: openTasks.size === 1 ? "Close the task" : "Close them",
            onClick: () =>
              openTasks.forEach((_t, id) =>
                patchTask.mutate(
                  { id, patch: { status: "done" } },
                  { onSuccess: () => void registry.cells.refetch() },
                ),
              ),
          },
        },
      );
    toast(
      targets.length === 1
        ? `${targets[0]!.p.code}: ${STATUS[next].label}`
        : `${targets.length} cells set to ${STATUS[next].label}`,
      {
        action: {
          label: "Undo",
          onClick: () =>
            void batch(targets, (t) => {
              const b = before.find((x) => x.t === t)!;
              return { status: b.status, reason: b.reason };
            }).catch(() => toast.error("Could not undo that.")),
        },
      },
    );
  }

  const targetsFor = (t: Target) =>
    selected.has(keyOf(t.p.id, t.c.id)) && selected.size > 1
      ? rows.flatMap((p) =>
          columns
            .filter((c) => selected.has(keyOf(p.id, c.id)) && applies(c, p))
            .map((c) => ({ p, c })),
        )
      : [t];

  function pick(e: MouseEvent, r: number, ci: number) {
    const p = rows[r]!;
    const c = columns[ci]!;
    const k = keyOf(p.id, c.id);
    if (e.shiftKey && anchor) {
      const next = new Set<string>();
      for (let i = Math.min(anchor.r, r); i <= Math.max(anchor.r, r); i++)
        for (let j = Math.min(anchor.c, ci); j <= Math.max(anchor.c, ci); j++)
          if (applies(columns[j]!, rows[i]!)) next.add(keyOf(rows[i]!.id, columns[j]!.id));
      setSelected(next);
      return;
    }
    if (e.metaKey || e.ctrlKey) {
      const next = new Set(selected);
      if (!next.delete(k)) next.add(k);
      setSelected(next);
      setAnchor({ r, c: ci });
      return;
    }
    setSelected(new Set([k]));
    setAnchor({ r, c: ci });
    setOpen({ p: p.id, c: c.id });
  }

  function onKey(e: KeyboardEvent, r: number, ci: number) {
    const move = (dr: number, dc: number) => {
      e.preventDefault();
      const nr = Math.min(rows.length - 1, Math.max(0, r + dr));
      const nc = Math.min(columns.length - 1, Math.max(0, ci + dc));
      grid.current?.querySelector<HTMLElement>(`[data-cell="${nr}-${nc}"]`)?.focus();
    };
    if (e.key === "ArrowDown") move(1, 0);
    else if (e.key === "ArrowUp") move(-1, 0);
    else if (e.key === "ArrowRight") move(0, 1);
    else if (e.key === "ArrowLeft") move(0, -1);
    else if (e.key === "Enter") {
      e.preventDefault();
      setOpen({ p: rows[r]!.id, c: columns[ci]!.id });
    } else if (e.key === "Escape") setOpen(undefined);
    else if (/^[1-7]$/.test(e.key) && !e.metaKey && !e.ctrlKey && !e.altKey) {
      e.preventDefault();
      const next = STATUSES[Number(e.key) - 1]!;
      const t = { p: rows[r]!, c: columns[ci]! };
      if (!canEdit) return;
      if (next.needsReason) setOpen({ p: t.p.id, c: t.c.id, initial: next.value });
      else void setStatusFor(targetsFor(t), next.value);
    }
  }

  const sel = rows.flatMap((p) =>
    columns.filter((c) => selected.has(keyOf(p.id, c.id)) && applies(c, p)).map((c) => ({ p, c })),
  );
  const bulkKind = REASON_KIND[bulk.status];
  const bulkReasons = reasons.filter((r) => r.active && r.kind === bulkKind);

  const clear = () => {
    setQ("");
    setGroup("");
    setStatus("");
    setOverdueOnly(false);
    setGapsOnly(false);
    setOwnerFilter("");
  };

  const activeFilters =
    [group, status, ownerFilter].filter(Boolean).length + Number(gapsOnly) + Number(overdueOnly);
  const showFilters = filtersOpen || view.filters || activeFilters > 0;
  const problems = problemCount ? problemCount.problems + problemCount.changed_since_verified : 0;

  const allTargets = participants.flatMap((p) =>
    allColumns.filter((c) => applies(c, p)).map((c) => ({ p, c })),
  );
  const startable = allTargets.filter((t) => cellOf(t.p, t.c)?.suggested_status === "in_progress");
  const changed = allTargets.filter((t) => cellOf(t.p, t.c)?.changed_since_verified);
  const unowned = allTargets.filter((t) => {
    const cell = cellOf(t.p, t.c);
    return !cell?.owner && ["missing", "not_started", "in_progress"].includes(statusOf(cell));
  });
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  const suggestions: Suggestion[] = [
    ...(canEdit && startable.length
      ? [
          {
            id: `start:${startable.length}`,
            text: `${plural(startable.length, "cell has", "cells have")} a file but ${startable.length === 1 ? "is" : "are"} marked not started.`,
            action: "Mark in progress",
            run: () => void setStatusFor(startable, "in_progress"),
          },
        ]
      : []),
    ...(canEdit && changed.length
      ? [
          {
            id: `changed:${changed.length}`,
            text: `${plural(changed.length, "document was", "documents were")} edited after you confirmed ${changed.length === 1 ? "it" : "them"}.`,
            action: "Mark needs review",
            run: () => void setStatusFor(changed, "needs_review"),
          },
        ]
      : []),
    ...(unowned.length > 5
      ? [
          {
            id: `owner:${unowned.length}`,
            text: `${unowned.length} open cells have no owner.`,
            action: "Show them",
            run: () => setOwnerFilter("none"),
          },
        ]
      : []),
  ].filter((x) => !dismissedPrefs.view.ids.includes(x.id));

  if (registry.participants.isLoading || registry.columns.isLoading) {
    return <Skeleton aria-label="Loading" className="h-64 w-full" />;
  }

  const add = canEdit && (
    <Button onClick={() => setDialog("add")}>
      <Plus aria-hidden /> Add participants
    </Button>
  );
  const openRow = open ? participants.find((p) => p.id === open.p) : undefined;
  const openCol = open ? columns.find((c) => c.id === open.c) : undefined;

  const strip: [string, string | number, () => void, boolean][] = [
    ["Participants", participants.length, clear, false],
    ["Complete", `${summary.percent}%`, clear, false],
    ["Missing", summary.missing, () => setStatus("missing"), status === "missing"],
    ["Overdue", summary.overdue, () => setOverdueOnly(true), overdueOnly],
    ["Needs review", summary.review, () => setStatus("needs_review"), status === "needs_review"],
    ["Archived", archived.length, () => setDialog("archived"), false],
  ];

  return (
    <div className="grid gap-4">
      <p role="note" className="text-sm text-muted-foreground">
        {CODES_ONLY}
      </p>
      {participants.length === 0 ? (
        <EmptyState
          icon={Users}
          title={
            archived.length > 0
              ? `All ${archived.length} ${archived.length === 1 ? "participant is" : "participants are"} archived.`
              : "No participants yet"
          }
          description={
            archived.length > 0
              ? canEdit
                ? "Show them to restore one, or add a new participant."
                : "Anyone who can see this project can see its participants. Only project editors can add them."
              : canEdit
                ? "Add your participants by code, like P-001. Then add the data each one should have, and see at a glance who is missing what."
                : "Anyone who can see this project can see its participants. Only project editors can add them."
          }
          footer={
            archived.length > 0 && (
              <Button variant="ghost" size="sm" onClick={() => setDialog("archived")}>
                Show {archived.length} archived
              </Button>
            )
          }
          action={
            add ? (
              <div className="flex flex-wrap justify-center gap-2">
                {add}
                {canColumns && (
                  <Button variant="outline" onClick={() => setDialog("import")}>
                    Import from a sheet
                  </Button>
                )}
                {/* A new study of people starts with only the default Consent form column. */}
                {canColumns && allColumns.every((c) => c.template_origin === "default") && (
                  <Button variant="outline" onClick={() => setDialog("template")}>
                    Start from a template
                  </Button>
                )}
              </div>
            ) : undefined
          }
        />
      ) : (
        <>
          <ul
            className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm"
            aria-label="Summary"
          >
            {strip
              .filter(
                ([label, value, , on]) =>
                  on || ["Participants", "Complete"].includes(label) || value !== 0,
              )
              .map(([label, value, onClick, on]) => (
                <li key={label}>
                  <button
                    type="button"
                    onClick={onClick}
                    aria-pressed={on}
                    className={cn(
                      "rounded-md px-1 py-0.5 text-muted-foreground hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                      on && "bg-muted text-foreground",
                      ["Missing", "Overdue"].includes(label) && value !== 0 && "text-danger-text",
                    )}
                  >
                    <span className="text-base font-semibold text-foreground">{value}</span>{" "}
                    {value === 1 && label === "Participants" ? "participant" : label.toLowerCase()}
                  </button>
                </li>
              ))}
          </ul>

          <Suggestions
            items={suggestions}
            onDismiss={(id) => dismissedPrefs.update({ ids: [...dismissedPrefs.view.ids, id] })}
          />

          <div
            className="flex flex-wrap items-center gap-2"
            role="search"
            aria-label="Filter participants"
          >
            <div className="relative">
              <Search
                aria-hidden
                className="absolute top-2.5 left-2.5 size-4 text-muted-foreground"
              />
              <Input
                aria-label="Search by code"
                placeholder="Search by code"
                className="w-44 pl-8"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </div>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Sort: ${sortLabel}, ${sort.dir === "asc" ? "ascending" : "descending"}`}
                  title={`Sort: ${sortLabel}`}
                >
                  <ArrowDownUp aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                {[
                  ["code", "Participant"],
                  ["group", "Group"],
                  ["done", "% done"],
                  ...columns.map((c) => [c.id, c.name] as [string, string]),
                ].map(([key, name]) => (
                  <DropdownMenuItem
                    key={key}
                    onSelect={() =>
                      sortPrefs.update({
                        key,
                        dir: sort.key === key && sort.dir === "asc" ? "desc" : "asc",
                      })
                    }
                  >
                    <span className="flex-1">{name}</span>
                    {sort.key === key &&
                      (sort.dir === "asc" ? (
                        <ArrowUp aria-hidden className="size-4" />
                      ) : (
                        <ArrowDown aria-hidden className="size-4" />
                      ))}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            <Button
              variant="ghost"
              aria-expanded={showFilters}
              onClick={() => {
                setFiltersOpen(!showFilters);
                if (view.filters) updateView({ filters: false });
              }}
            >
              <SlidersHorizontal aria-hidden /> Filters
              {activeFilters > 0 && (
                <span className="ml-1 rounded-full bg-primary px-1.5 text-xs text-primary-foreground">
                  {activeFilters}
                </span>
              )}
            </Button>
            <div className="ml-auto flex items-center gap-2">
              {add}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="More actions"
                    className="relative"
                  >
                    <MoreHorizontal aria-hidden />
                    {!!problems && (
                      <span className="absolute top-1 right-1 size-2 rounded-full bg-danger" />
                    )}
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {canColumns && (
                    <DropdownMenuItem onSelect={() => setDialog("columns")}>
                      Columns
                    </DropdownMenuItem>
                  )}
                  {canColumns && (
                    <DropdownMenuItem onSelect={() => setDialog("template")}>
                      Start from a template
                    </DropdownMenuItem>
                  )}
                  {canColumns && (
                    <DropdownMenuItem onSelect={() => setDialog("import")}>Import</DropdownMenuItem>
                  )}
                  {canColumns && (
                    <DropdownMenuItem onSelect={() => setDialog("match")}>
                      Match files
                    </DropdownMenuItem>
                  )}
                  {canColumns && (
                    <DropdownMenuItem onSelect={() => setDialog("history")}>
                      Import history
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem onSelect={() => setDialog("rules")}>
                    Rules and flow
                  </DropdownMenuItem>
                  <DropdownMenuItem onSelect={() => setDialog("health")}>
                    Link health{problems ? ` (${problems})` : ""}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onSelect={() => setDialog("customize")}>
                    Customize view
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>

          {showFilters && (
            <div
              className="flex flex-wrap items-center gap-2"
              aria-label="More filters"
              role="group"
            >
              <NativeSelect
                aria-label="Group"
                className="w-40"
                value={group}
                onChange={(e) => setGroup(e.target.value)}
              >
                <option value="">All groups</option>
                {groups.map((g) => (
                  <option key={g}>{g}</option>
                ))}
              </NativeSelect>
              <NativeSelect
                aria-label="Cell status"
                className="w-44"
                value={status}
                onChange={(e) => setStatus(e.target.value as CellStatus | "")}
              >
                <option value="">Any status</option>
                {STATUSES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </NativeSelect>
              <NativeSelect
                aria-label="Owner"
                className="w-40"
                value={ownerFilter}
                onChange={(e) => setOwnerFilter(e.target.value as typeof ownerFilter)}
              >
                <option value="">Any owner</option>
                <option value="me">Waiting on me</option>
                <option value="others">Waiting on others</option>
                <option value="none">Unassigned</option>
              </NativeSelect>
              <label className="flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={gapsOnly}
                  onChange={(e) => setGapsOnly(e.target.checked)}
                />
                Only with gaps
              </label>
              <label className="flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={overdueOnly}
                  onChange={(e) => setOverdueOnly(e.target.checked)}
                />
                Overdue
              </label>
              {activeFilters > 0 && (
                <Button variant="ghost" size="sm" onClick={clear}>
                  Clear
                </Button>
              )}
            </div>
          )}

          {allColumns.length === 0 && (
            <EmptyState
              title="No data columns yet"
              description={
                canColumns
                  ? "Add the pieces of data each participant should have, like a transcript or a questionnaire."
                  : "Columns are the pieces of data each participant should have, like a transcript or a questionnaire. Only project leads can add them, so ask your project lead."
              }
              action={
                canColumns ? (
                  <div className="flex flex-wrap justify-center gap-2">
                    <Button onClick={() => setDialog("template")}>Start from a template</Button>
                    <Button variant="outline" onClick={() => setDialog("columns")}>
                      Add columns
                    </Button>
                  </div>
                ) : undefined
              }
            />
          )}
          <div className="flex flex-col items-start gap-4 lg:flex-row">
            <div className="min-w-0 flex-1 self-stretch">
              {/* Narrow screens: a list of participants, each opening into its checklist. */}
              <ul className="grid gap-2 md:hidden" aria-label="Participants">
                {rows.map((p) => (
                  <li key={p.id} className="rounded-lg border bg-card">
                    <details>
                      <summary className="flex min-h-11 cursor-pointer items-center justify-between px-3 py-2">
                        <span className="font-medium">{p.code}</span>
                        <span className="text-sm text-muted-foreground">
                          {
                            completeness(
                              columns.filter((c) => applies(c, p)).map((c) => cellOf(p, c)),
                            ).percent
                          }
                          % complete
                        </span>
                      </summary>
                      <ul className="grid gap-1 px-3 pb-3">
                        {columns
                          .filter((c) => applies(c, p))
                          .map((c) => (
                            <li key={c.id} className="flex items-center justify-between gap-2">
                              <button
                                type="button"
                                className="min-h-10 flex-1 text-left text-sm"
                                onClick={() => setOpen({ p: p.id, c: c.id })}
                              >
                                {c.name}
                              </button>
                              <StatusChip
                                status={statusOf(cellOf(p, c))}
                                files={cellOf(p, c)?.files.length}
                              />
                            </li>
                          ))}
                      </ul>
                    </details>
                  </li>
                ))}
              </ul>

              <div className="hidden max-h-[70vh] overflow-auto rounded-lg border md:block">
                <table
                  ref={grid}
                  role="grid"
                  aria-label="Participant data completeness"
                  aria-rowcount={rows.length + 1}
                  aria-colcount={columns.length + 2}
                  className="w-full border-separate border-spacing-0 text-sm"
                >
                  <thead>
                    <tr>
                      <th
                        scope="col"
                        className="sticky top-0 left-0 z-30 border-b border-r bg-background px-3 py-2 text-left font-medium"
                      >
                        Participant
                      </th>
                      {columns.map((c) => (
                        <th
                          key={c.id}
                          scope="col"
                          title={c.required ? undefined : "Optional"}
                          className="sticky top-0 z-20 min-w-36 border-b bg-background px-3 py-2 text-left font-medium"
                        >
                          {c.name}
                          {!c.required && (
                            <span className="ml-1 text-xs font-normal text-muted-foreground">
                              (optional)
                            </span>
                          )}
                        </th>
                      ))}
                      {view.totals && (
                        <th
                          scope="col"
                          className="sticky top-0 z-20 border-b bg-background px-3 py-2 text-left font-medium"
                        >
                          Done
                        </th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((p, r) => (
                      <Fragment key={p.id}>
                        <tr>
                          <th
                            scope="row"
                            className="sticky left-0 z-10 border-b border-r bg-background px-3 py-1 text-left font-medium"
                          >
                            <button
                              type="button"
                              aria-expanded={expanded.has(p.id)}
                              aria-label={`${expanded.has(p.id) ? "Hide" : "Show"} details for ${p.code}`}
                              className="mr-1 inline-flex size-5 items-center justify-center rounded text-muted-foreground hover:bg-muted"
                              onClick={() =>
                                setExpanded((prev) => {
                                  const next = new Set(prev);
                                  if (!next.delete(p.id)) next.add(p.id);
                                  return next;
                                })
                              }
                            >
                              <ChevronRight
                                aria-hidden
                                className={cn(
                                  "size-4 transition-transform",
                                  expanded.has(p.id) && "rotate-90",
                                )}
                              />
                            </button>
                            <Link
                              className="underline-offset-2 hover:underline"
                              to={`/labs/${labId}/projects/${projectId}/participants/${p.id}`}
                            >
                              {p.code}
                            </Link>
                            {p.group && (
                              <span className="block text-xs font-normal text-muted-foreground">
                                {p.group}
                              </span>
                            )}
                          </th>
                          {columns.map((c, ci) => {
                            if (!applies(c, p))
                              return (
                                <td
                                  key={c.id}
                                  className="border-b px-3 text-muted-foreground"
                                  title={`${c.name} does not apply to ${p.group || "this group"}`}
                                >
                                  <span aria-hidden>–</span>
                                  <span className="sr-only">Does not apply to this group</span>
                                </td>
                              );
                            const cell = cellOf(p, c);
                            const s = statusOf(cell);
                            const reason = reasons.find((x) => x.id === cell?.reason)?.label;
                            const isSel = selected.has(keyOf(p.id, c.id));
                            return (
                              <td
                                key={c.id}
                                role="gridcell"
                                aria-selected={isSel}
                                className="border-b p-0"
                              >
                                <button
                                  type="button"
                                  data-cell={`${r}-${ci}`}
                                  aria-label={`${p.code}, ${c.name}, ${STATUS[s].label}${
                                    reason ? `, reason: ${reason}` : ""
                                  }`}
                                  tabIndex={r === 0 && ci === 0 ? 0 : -1}
                                  onClick={(e) => pick(e, r, ci)}
                                  onKeyDown={(e) => onKey(e, r, ci)}
                                  className={cn(
                                    "flex w-full items-center px-3 text-left focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none focus-visible:ring-inset",
                                    density === "compact" ? "py-0.5" : "py-2",
                                    isSel && "bg-primary/10",
                                  )}
                                >
                                  <StatusChip status={s} files={cell?.files.length} />
                                  {isOverdue(cell, today) && (
                                    <span className="ml-1 text-xs text-danger-text">Overdue</span>
                                  )}
                                </button>
                              </td>
                            );
                          })}
                          {view.totals && (
                            <td className="border-b px-3 text-muted-foreground">
                              {
                                completeness(
                                  allColumns.filter((c) => applies(c, p)).map((c) => cellOf(p, c)),
                                ).percent
                              }
                              %
                            </td>
                          )}
                        </tr>
                        {expanded.has(p.id) && (
                          <tr>
                            <td
                              colSpan={columns.length + 2}
                              className="border-b bg-muted/40 px-3 py-2 text-sm"
                            >
                              <ParticipantDetail
                                participant={p}
                                columns={columns}
                                cellOf={(c) => cellOf(p, c)}
                                href={`/labs/${labId}/projects/${projectId}/participants/${p.id}`}
                              />
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    ))}
                  </tbody>
                  {view.totals && (
                    <tfoot>
                      <tr>
                        <th
                          scope="row"
                          className="sticky bottom-0 left-0 z-20 border-t border-r bg-background px-3 py-2 text-left font-medium"
                        >
                          Complete
                        </th>
                        {columns.map((c) => (
                          <td
                            key={c.id}
                            className="sticky bottom-0 z-10 border-t bg-background px-3 py-2 text-muted-foreground"
                          >
                            {
                              completeness(
                                participants.filter((p) => applies(c, p)).map((p) => cellOf(p, c)),
                              ).percent
                            }
                            %
                          </td>
                        ))}
                        <td className="sticky bottom-0 z-10 border-t bg-background" />
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
              {rows.length === 0 && (
                <EmptyState
                  className="mt-3"
                  title="No participants match"
                  description="Try clearing a filter."
                  action={
                    <Button variant="outline" onClick={clear}>
                      Clear filters
                    </Button>
                  }
                />
              )}
              {view.help && columns.length > 0 && (
                <p className="mt-2 hidden text-xs text-muted-foreground md:block">
                  Arrow keys move, Enter opens a cell, keys 1 to 7 set a status (
                  {STATUSES.map((s) => `${s.key} ${s.label}`).join(", ")}). Shift-click selects a
                  range.
                </p>
              )}
            </div>
            {openRow && openCol && (
              <CellPanel
                key={`${openRow.id}:${openCol.id}:${open?.initial ?? ""}`}
                labId={labId}
                projectId={projectId}
                participant={openRow}
                column={openCol}
                cell={cellOf(openRow, openCol)}
                registry={registry}
                canEdit={canEdit}
                initialStatus={open?.initial}
                onClose={() => setOpen(undefined)}
              />
            )}
          </div>
        </>
      )}

      {canEdit && sel.length > 1 && (
        <div
          role="region"
          aria-label="Change selected cells"
          className="fixed inset-x-4 bottom-4 z-40 mx-auto flex max-w-3xl flex-wrap items-center gap-2 rounded-xl border bg-card p-3 shadow-lg"
        >
          <span className="text-sm font-medium">{sel.length} cells selected</span>
          <NativeSelect
            aria-label="Set status"
            className="w-44"
            value={bulk.status}
            onChange={(e) => setBulk({ status: e.target.value as CellStatus, reason: "" })}
          >
            {STATUSES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </NativeSelect>
          {bulkKind && (
            <NativeSelect
              aria-label="Reason"
              className="w-48"
              value={bulk.reason}
              onChange={(e) => setBulk({ ...bulk, reason: e.target.value })}
            >
              <option value="">Choose a reason…</option>
              {bulkReasons.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
            </NativeSelect>
          )}
          <Button
            disabled={!!bulkKind && !bulk.reason}
            onClick={() => void setStatusFor(sel, bulk.status, bulk.reason || undefined)}
          >
            Apply
          </Button>
          <span className="mx-1 hidden h-6 border-l sm:inline" aria-hidden />
          <NativeSelect
            aria-label="Owner for selected cells"
            className="w-40"
            value={bulkOwner}
            onChange={(e) => setBulkOwner(e.target.value)}
          >
            <option value="">Owner…</option>
            {members.map((m) => (
              <option key={m.id} value={m.user.id}>
                {personName(m.user)}
              </option>
            ))}
          </NativeSelect>
          <Input
            aria-label="Due date for selected cells"
            type="date"
            className="w-40"
            value={bulkDue}
            onChange={(e) => setBulkDue(e.target.value)}
          />
          <Button
            variant="outline"
            disabled={!bulkOwner && !bulkDue}
            onClick={() =>
              void batch(sel, () => ({
                ...(bulkOwner && { owner: bulkOwner }),
                ...(bulkDue && { due_date: bulkDue }),
              }))
                .then(() => toast.success(`Updated ${sel.length} cells`))
                .catch(() => toast.error("Some cells were not updated."))
            }
          >
            Set owner and due date
          </Button>
          <NativeSelect
            aria-label="How to make tasks"
            className="w-44"
            value={taskMode}
            onChange={(e) => setTaskMode(e.target.value as typeof taskMode)}
          >
            <option value="cell">One task per cell</option>
            <option value="participant">One per participant</option>
            <option value="component">One per column</option>
          </NativeSelect>
          <Button
            variant="outline"
            onClick={() =>
              registry.createTasks.mutate(
                {
                  cells: sel.map((t) => ({ participant: t.p.id, component: t.c.id })),
                  mode: taskMode,
                  assignee: bulkOwner || null,
                  due_date: bulkDue || null,
                },
                {
                  onSuccess: (r) =>
                    toast.success(
                      `${r.created} task${r.created === 1 ? "" : "s"} created${
                        r.skipped ? `, ${r.skipped} cell${r.skipped === 1 ? "" : "s"} skipped` : ""
                      }`,
                    ),
                  onError: (e) =>
                    toast.error(
                      formErrors(e, ["assignee"]).fields.assignee ?? "Could not create tasks.",
                    ),
                },
              )
            }
          >
            Create tasks
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Clear selection"
            onClick={() => setSelected(new Set())}
          >
            <X aria-hidden />
          </Button>
        </div>
      )}

      {dialog &&
        ["import", "history", "match", "health"].includes(dialog) &&
        (() => {
          const common = { labId, projectId, onClose: () => setDialog(null) };
          return dialog === "import" ? (
            <ImportWizard {...common} />
          ) : dialog === "history" ? (
            <ImportHistory {...common} />
          ) : dialog === "match" ? (
            <MatchFilesDialog {...common} />
          ) : (
            <LinkHealthDialog {...common} />
          );
        })()}
      {dialog === "rules" && (
        <RulesDialog
          labId={labId}
          projectId={projectId}
          canEdit={canColumns}
          canExport={project.my_permissions.includes("export")}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "template" && (
        <TemplatePicker registry={registry} existing={allColumns} onClose={() => setDialog(null)} />
      )}
      {dialog === "customize" && (
        <CustomizePanel
          columns={allColumns}
          view={view}
          onChange={updateView}
          onReset={resetView}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "archived" && (
        <ArchivedDialog
          registry={registry}
          archived={archived}
          canEdit={canEdit}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "add" && (
        <AddParticipantsDialog registry={registry} onClose={() => setDialog(null)} />
      )}
      {dialog === "columns" && (
        <ColumnsDialog
          registry={registry}
          columns={columns}
          cellCounts={cellCounts}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  );
}
