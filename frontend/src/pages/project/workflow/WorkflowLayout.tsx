import { useIsMutating } from "@tanstack/react-query";
import { Check, FlaskConical, GitBranch, Minus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, Navigate, NavLink, Outlet, useLocation, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useLab } from "@/hooks/workspace";
import { useWorkflowProgress } from "@/hooks/workflow";
import { isKind } from "@/lib/research";
import { cn } from "@/lib/utils";
import { NEXT_STEP, SECTIONS, sectionOf, type Section } from "@/lib/workflow";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { SectionLists } from "@/pages/project/ResearchTab";
import { DmpPanel } from "@/pages/project/workflow/DmpPanel";
import { fail } from "@/pages/project/workflow/parts";

const nameOf = (s: string) => SECTIONS.find(([k]) => k === s)?.[1] ?? s;

/** Funding is for PIs only (D226); the server already leaves it out of `stages`. */
const shownSections = (p: ProjectTabProps["project"]) =>
  SECTIONS.filter(([key]) => key !== "funding" || p.my_permissions.includes("access_funding"));

/** The Workflow tab: a progress bar over Funding through Review (D132), then the open stage. */
export function WorkflowLayout(props: ProjectTabProps) {
  const { labId, projectId, project } = props;
  const { progress, mark } = useWorkflowProgress(labId, projectId);
  const { pathname } = useLocation();
  const archived = project.status === "archived";
  const canEdit = project.my_permissions.includes("edit_content") && !archived;
  const [asking, setAsking] = useState(false);
  const inventoryOn = useLab(labId).data?.inventory_enabled;

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
        {archived && (
          <p role="status" className="rounded-lg bg-muted p-3 text-sm font-medium">
            Archived. Set it back to Active to make changes.
          </p>
        )}
        <nav aria-label="Workflow sections" className="overflow-x-auto py-1">
          <ol className="flex min-w-max">
            {shownSections(project).map(([key, name]) => {
              const stage = stages.find((s) => s.key === key);
              const isNext = key === next;
              // Three different things: finished, skipped on purpose, and the one to do now.
              const notNeeded = !!stage?.marked && !stage.recorded;
              const finished = !!stage?.done && !notNeeded;
              return (
                <li
                  key={key}
                  className={cn(
                    "relative min-w-20 flex-1 after:absolute after:top-3.5 after:left-1/2 after:h-0.5 after:w-full after:bg-border last:after:hidden",
                    finished && "after:bg-primary",
                  )}
                >
                  <NavLink
                    to={key}
                    aria-label={
                      notNeeded
                        ? `${name} (not needed)`
                        : finished
                          ? `${name} (done)`
                          : isNext
                            ? `${name} (do this next)`
                            : undefined
                    }
                    className={({ isActive }) =>
                      cn(
                        "relative z-10 flex flex-col items-center gap-1 rounded-md px-1 py-0.5 text-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                        isNext ? "font-bold" : "font-medium",
                        isActive
                          ? "text-primary underline decoration-2 underline-offset-4"
                          : notNeeded
                            ? "text-muted-foreground/70 hover:text-foreground"
                            : isNext
                              ? "text-foreground"
                              : "text-muted-foreground hover:text-foreground",
                      )
                    }
                  >
                    <span
                      aria-hidden
                      className={cn(
                        "grid size-6 place-items-center rounded-full border-2 [&_svg]:size-3.5",
                        finished
                          ? "border-primary bg-primary text-primary-foreground"
                          : notNeeded
                            ? "border-dashed border-muted-foreground/40 bg-muted text-muted-foreground"
                            : isNext
                              ? "border-primary bg-background ring-4 ring-primary/30"
                              : "border-border bg-background",
                      )}
                    >
                      {finished && <Check strokeWidth={3} />}
                      {notNeeded && <Minus strokeWidth={3} />}
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
                <span className="font-semibold">
                  {canEdit ? "Do this next" : "Next step"}: {nameOf(next)}.
                </span>{" "}
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
            {canEdit && next && next !== open && (
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
                  openStage.marked
                    ? mark.mutate({ stage: openStage.key, done: false }, { onError: fail })
                    : setAsking(true)
                }
              >
                {openStage.marked ? "Mark as not done" : "Done or not needed"}
              </Button>
            )}
            {inventoryOn && (
              <Button size="sm" variant="outline" asChild>
                <NavLink to="protocols">
                  <FlaskConical aria-hidden /> Protocols
                </NavLink>
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
      {canEdit && openStage && !openStage.done && (
        <p className="-mt-3 text-xs text-muted-foreground">
          Done means this step is finished, or you do not need it for this project.
        </p>
      )}
      <Dialog open={asking} onOpenChange={setAsking}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">Mark as done?</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            Mark {nameOf(open ?? "")} done or not needed? You can undo this later.
          </DialogDescription>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button
              disabled={mark.isPending}
              onClick={() =>
                openStage &&
                mark.mutate(
                  { stage: openStage.key, done: true },
                  { onError: fail, onSettled: () => setAsking(false) },
                )
              }
            >
              Mark done
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      <Outlet context={props} />
    </div>
  );
}

/** Opens on the first stage not done yet; the last stage once every stage is done. */
export function WorkflowIndex({ labId, projectId }: ProjectTabProps) {
  const { data, isError } = useWorkflowProgress(labId, projectId).progress;
  if (isError) return <Navigate to="ethics" replace />;
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
