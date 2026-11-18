import { ArrowDown, ArrowUp, SlidersHorizontal } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { MoreMenu } from "@/components/shared/MoreMenu";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useViewPrefs } from "@/hooks/viewPrefs";
import { useUpdateProject } from "@/hooks/projects";
import type { DashProject } from "@/hooks/dashboard";
import { addDays } from "@/lib/snooze";
import { localDateISO } from "@/lib/format";

/** The parts of Home that can be hidden or moved, in their default order. */
export const HOME_SECTIONS = [
  { id: "recent", label: "Recent documents and files" },
  { id: "people", label: "Team" },
  { id: "activity", label: "Activity" },
] as const;
export type HomeSection = (typeof HOME_SECTIONS)[number]["id"];

interface HomePrefs {
  hidden: HomeSection[];
  order: HomeSection[];
}
const DEFAULT_HOME: HomePrefs = { hidden: [], order: HOME_SECTIONS.map((s) => s.id) };

/** Which parts of Home show, and in what order. Kept in this browser, per lab. */
export function useHomeLayout(labId: string) {
  const { view, update, reset } = useViewPrefs<HomePrefs>("home", labId, DEFAULT_HOME);
  // a section added later still shows, after the ones the person has placed
  const order = [
    ...view.order.filter((id) => HOME_SECTIONS.some((s) => s.id === id)),
    ...HOME_SECTIONS.map((s) => s.id).filter((id) => !view.order.includes(id)),
  ];
  const shown = order.filter((id) => !view.hidden.includes(id));
  const move = (id: HomeSection, by: -1 | 1) => {
    const i = order.indexOf(id);
    const j = i + by;
    if (j < 0 || j >= order.length) return;
    const next = [...order];
    [next[i], next[j]] = [next[j]!, next[i]!];
    update({ order: next });
  };
  const toggle = (id: HomeSection) =>
    update({
      hidden: view.hidden.includes(id) ? view.hidden.filter((h) => h !== id) : [...view.hidden, id],
    });
  return { order, shown, hidden: view.hidden, move, toggle, reset };
}

/** "Customize" on Home: hide a part, or move it up or down. */
export function CustomizeHome({ layout }: { layout: ReturnType<typeof useHomeLayout> }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" aria-label="Customize Home">
          <SlidersHorizontal aria-hidden /> Customize
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72 p-2">
        <DropdownMenuLabel>Parts of Home</DropdownMenuLabel>
        <ul className="grid gap-1">
          {layout.order.map((id, i) => {
            const label = HOME_SECTIONS.find((s) => s.id === id)!.label;
            return (
              <li key={id} className="flex items-center gap-1 text-sm">
                <label className="flex min-w-0 flex-1 items-center gap-2 rounded px-2 py-1 hover:bg-accent">
                  <input
                    type="checkbox"
                    checked={!layout.hidden.includes(id)}
                    onChange={() => layout.toggle(id)}
                  />
                  <span className="truncate">{label}</span>
                </label>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-7"
                  aria-label={`Move ${label} up`}
                  disabled={i === 0}
                  onClick={() => layout.move(id, -1)}
                >
                  <ArrowUp aria-hidden />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-7"
                  aria-label={`Move ${label} down`}
                  disabled={i === layout.order.length - 1}
                  onClick={() => layout.move(id, 1)}
                >
                  <ArrowDown aria-hidden />
                </Button>
              </li>
            );
          })}
        </ul>
        <Button variant="ghost" size="sm" className="mt-2" onClick={layout.reset}>
          Show everything
        </Button>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

interface SnoozePrefs {
  /** Attention card id -> the last day it stays hidden (YYYY-MM-DD). */
  until: Record<string, string>;
}

/** "Needs attention" cards can rest for a week, so a known gap does not nag. Kept in this browser. */
export function useSnooze(labId: string) {
  const { view, update } = useViewPrefs<SnoozePrefs>("home-snooze", labId, { until: {} });
  const today = localDateISO();
  const resting = (id: string) => (view.until[id] ?? "") >= today;
  return {
    resting,
    restingIds: Object.keys(view.until).filter(resting),
    snooze: (id: string, days = 7) =>
      update({ until: { ...view.until, [id]: addDays(today, days) } }),
    wake: (id: string) => {
      const next = { ...view.until };
      delete next[id];
      update({ until: next });
    },
    wakeAll: () => update({ until: {} }),
  };
}

/** Quick actions on a project row, so the common jobs do not need a click into the project. */
export function ProjectRowActions({ labId, project }: { labId: string; project: DashProject }) {
  const update = useUpdateProject(labId, project.id);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const base = `/labs/${labId}/projects/${project.id}`;
  const live = project.status !== "completed" && project.status !== "archived";
  const set = (status: "completed" | "archived" | "active", done: string) =>
    update.mutate(
      { status },
      {
        onSuccess: () => {
          toast.success(done);
          void qc.invalidateQueries({ queryKey: ["labs", labId] });
        },
        onError: () => toast.error("Could not change the project."),
      },
    );
  return (
    <div className="flex items-center justify-end gap-1">
      {live && (
        <Button variant="ghost" size="sm" asChild>
          <Link to={`${base}/tasks?new=task`} aria-label={`New task in ${project.name}`}>
            + Task
          </Link>
        </Button>
      )}
      <MoreMenu
        label={`More for ${project.name}`}
        items={[
          live && {
            label: "Add deadline",
            onSelect: () => void navigate(`${base}/overview?new=deadline`),
          },
          { label: "Open files", onSelect: () => void navigate(`${base}/documents`) },
          live && {
            label: "Mark complete",
            onSelect: () => set("completed", `${project.name} marked complete`),
          },
          live && {
            label: "Archive",
            onSelect: () => set("archived", `${project.name} archived`),
          },
          !live && {
            label: "Set back to active",
            onSelect: () => set("active", `${project.name} is active again`),
          },
        ]}
      />
    </div>
  );
}
