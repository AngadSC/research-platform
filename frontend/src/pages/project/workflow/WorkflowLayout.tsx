import { useIsMutating } from "@tanstack/react-query";
import { Check, GitBranch } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link, Navigate, NavLink, Outlet, useLocation, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkflowProgress } from "@/hooks/workflow";
import { isKind } from "@/lib/research";
import { cn } from "@/lib/utils";
import { NEXT_STEP, SECTIONS, sectionOf, type Section } from "@/lib/workflow";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { SectionLists } from "@/pages/project/ResearchTab";
import { DmpPanel } from "@/pages/project/workflow/DmpPanel";
import { fail } from "@/pages/project/workflow/parts";

const nameOf = (s: string) => SECTIONS.find(([k]) => k === s)?.[1] ?? s;

/** The Workflow tab: a progress bar over Funding through Review (D132), then the open stage. */
export function WorkflowLayout(props: ProjectTabProps) {
  const { labId, projectId, project } = props;
  const { progress, mark } = useWorkflowProgress(labId, projectId);
  const { pathname } = useLocation();
  const canEdit = project.my_permissions.includes("edit_content");

  // Saving a record on any stage can finish it, so check again when a save ends.
  const { refetch } = progress;
  const saving = useIsMutating();
  const wasSaving = useRef(0);
  useEffect(() => {
    if (wasSaving.current && !saving) void refetch();
    wasSaving.current = saving;
  }, [saving, refetch]);

  const stages = progress.data?.stages ?? [];
  const next = progress.data?.next as Section | null | undefined;
  const open = pathname.split("/workflow/")[1]?.split("/")[0];
  const openStage = stages.find((s) => s.key === open);
  const doneCount = stages.filter((s) => s.done).length;

  return (
    <div className="grid gap-6">
      <div className="grid gap-3">
        <nav aria-label="Workflow sections" className="overflow-x-auto py-1">
          <ol className="flex min-w-max">
            {SECTIONS.map(([key, name]) => {
              const stage = stages.find((s) => s.key === key);
              const isNext = key === next;
              return (
                <li
                  key={key}
                  className={cn(
                    "relative min-w-20 flex-1 after:absolute after:top-3.5 after:left-1/2 after:h-0.5 after:w-full after:bg-border last:after:hidden",
                    stage?.done && "after:bg-primary",
                  )}
                >
                  <NavLink
                    to={key}
                    aria-label={
                      stage?.done ? `${name} (done)` : isNext ? `${name} (do this next)` : undefined
                    }
                    className={({ isActive }) =>
                      cn(
                        "relative z-10 flex flex-col items-center gap-1 rounded-md px-1 py-0.5 text-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                        isActive
                          ? "font-semibold text-primary"
                          : "font-medium text-muted-foreground hover:text-foreground",
                      )
                    }
                  >
                    <span
                      aria-hidden
                      className={cn(
                        "grid size-6 place-items-center rounded-full border-2 [&_svg]:size-3.5",
                        stage?.done
                          ? "border-primary bg-primary text-primary-foreground"
                          : isNext
                            ? "border-primary bg-background ring-2 ring-primary/30"
                            : "border-border bg-background",
                      )}
                    >
                      {stage?.done && <Check strokeWidth={3} />}
                    </span>
                    {name}
                  </NavLink>
                </li>
              );
            })}
          </ol>
        </nav>
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-muted p-3">
          <p className="text-sm">
            {next ? (
              <>
                <span className="font-semibold">Do this next: {nameOf(next)}.</span>{" "}
                {NEXT_STEP[next]}
              </>
            ) : next === null ? (
              <span className="font-semibold">Every stage is done.</span>
            ) : null}
            {stages.length > 0 && (
              <span className="ml-2 text-xs text-muted-foreground">
                {doneCount} of {stages.length} done
              </span>
            )}
          </p>
          <div className="flex flex-wrap gap-2">
            {next && next !== open && (
              <Button size="sm" asChild>
                <Link to={next}>Go to {nameOf(next)}</Link>
              </Button>
            )}
            {canEdit && openStage && (!openStage.done || openStage.marked) && (
              <Button
                size="sm"
                variant="outline"
                disabled={mark.isPending}
                onClick={() =>
                  mark.mutate({ stage: openStage.key, done: !openStage.marked }, { onError: fail })
                }
              >
                {openStage.marked ? "Mark as not done" : "Done or not needed"}
              </Button>
            )}
            <Button size="sm" variant="outline" asChild>
              <NavLink to="lineage">
                <GitBranch aria-hidden /> Lineage
              </NavLink>
            </Button>
          </div>
        </div>
      </div>
      <Outlet context={props} />
    </div>
  );
}

/** Opens on the first stage not done yet; the last stage once every stage is done. */
export function WorkflowIndex({ labId, projectId }: ProjectTabProps) {
  const { data, isError } = useWorkflowProgress(labId, projectId).progress;
  if (isError) return <Navigate to="funding" replace />;
  if (!data) return <Skeleton aria-label="Loading" className="h-40 w-full" />;
  return <Navigate to={data.next ?? "review"} replace />;
}

export const DataTab = (p: ProjectTabProps) => (
  <div className="grid gap-8">
    <DmpPanel {...p} />
    <SectionLists {...p} section="data" />
  </div>
);
export const AnalysisTab = (p: ProjectTabProps) => <SectionLists {...p} section="analysis" />;
export const ManuscriptTab = (p: ProjectTabProps) => <SectionLists {...p} section="manuscript" />;

/** `/research/<kind>[/new|/<id>]` from before the Workflow tab goes to its new place (D132). */
export function ResearchRedirect() {
  const { labId, projectId, "*": rest = "" } = useParams();
  const { search } = useLocation();
  const [kind, ...tail] = rest.split("/").filter(Boolean);
  const base = `/labs/${labId}/projects/${projectId}/workflow`;
  const to = isKind(kind)
    ? [base, sectionOf(kind), ...(tail.length ? [kind, ...tail] : [])].join("/")
    : `${base}/data`;
  return <Navigate to={to + search} replace />;
}

/** `/lineage` from before it moved inside Workflow, keeping `?focus=`. */
export function LineageRedirect() {
  const { search } = useLocation();
  return <Navigate to={`../workflow/lineage${search}`} relative="path" replace />;
}
