import { Archive, ArrowLeft, Check, ChevronLeft, ChevronRight, Paperclip } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { Disclosure } from "@/components/shared/Disclosure";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useParticipantEvents, useReasons, useRegistry } from "@/hooks/participants";
import type { CellStatus } from "@/lib/api-types";
import { CATEGORIES, completeness, statusOf } from "@/lib/participants";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { ParticipantFiles } from "@/pages/project/participants/ParticipantFiles";
import { StatusChip } from "@/pages/project/participants/StatusChip";
import { RelativeTime } from "@/components/shared/RelativeTime";

/** One participant: every data column as a checklist, grouped by type, with their history. */
export default function ParticipantPage({ labId, projectId, project }: ProjectTabProps) {
  const { participantId = "" } = useParams();
  const navigate = useNavigate();
  const registry = useRegistry(labId, projectId);
  const reasons = useReasons(labId).data ?? [];
  const events = useParticipantEvents(labId, projectId, participantId).data ?? [];
  const list = registry.participants.data ?? [];
  const index = list.findIndex((p) => p.id === participantId);
  const p = list[index];
  const back = `/labs/${labId}/projects/${projectId}/participants`;
  const canEdit = project.my_permissions.includes("edit_content");
  const [showDone, setShowDone] = useState(false);

  if (registry.participants.isLoading) return <Skeleton aria-label="Loading" className="h-48" />;
  if (!p)
    return (
      <EmptyState
        title="Participant not found"
        description="They may have been archived. You can restore them from the participants page."
        action={
          <Button asChild>
            <Link to={back}>Back to participants</Link>
          </Button>
        }
      />
    );

  const columns = (registry.columns.data ?? []).filter(
    (c) => c.applies_to_groups.length === 0 || c.applies_to_groups.includes(p.group),
  );
  const cells = registry.cells.data ?? [];
  const cellOf = (componentId: string) =>
    cells.find((c) => c.participant === p.id && c.component === componentId);
  const { percent } = completeness(columns.map((c) => cellOf(c.id)));
  // "Done" is complete or deliberately left out; everything else is still to do.
  const isDone = (id: string) => ["complete", "excluded"].includes(statusOf(cellOf(id)));
  const todo = columns.filter((c) => !isDone(c.id));
  const doneCount = columns.length - todo.length;
  const step = (d: number) => {
    const next = list[index + d];
    if (next) void navigate(`${back}/${next.id}`);
  };
  // D308: participants are archived, never deleted, so archiving offers Undo.
  const archive = () =>
    registry.archive.mutate(
      { id: p.id, archived: true },
      {
        onSuccess: () => {
          toast.success(`${p.code} archived`, {
            action: {
              label: "Undo",
              onClick: () => registry.archive.mutate({ id: p.id, archived: false }),
            },
          });
          void navigate(back);
        },
        onError: () => toast.error(`Couldn't archive ${p.code}`),
      },
    );
  // One click for the common case, like recording that a consent form came in. Anything that
  // needs a reason (Missing and the like) is set from the grid's cell panel.
  const markComplete = (componentId: string, name: string) => {
    const cell = cellOf(componentId);
    const undo = { status: statusOf(cell), reason: cell?.reason ?? null };
    registry.setCell.mutate(
      { participant: p.id, component: componentId, patch: { status: "complete" } },
      {
        onSuccess: () =>
          toast.success(`${p.code}: ${name} complete`, {
            action: {
              label: "Undo",
              onClick: () =>
                registry.setCell.mutate({ participant: p.id, component: componentId, patch: undo }),
            },
          }),
        onError: () => toast.error(`Couldn't update ${name}`),
      },
    );
  };

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-center gap-3">
        <Button asChild variant="ghost" size="sm">
          <Link to={back}>
            <ArrowLeft aria-hidden /> All participants
          </Link>
        </Button>
        <div className="ml-auto flex gap-2">
          {canEdit && (
            <Button
              variant="outline"
              size="sm"
              disabled={registry.archive.isPending}
              onClick={archive}
            >
              <Archive aria-hidden /> Archive
            </Button>
          )}
          <Button variant="outline" size="sm" disabled={index <= 0} onClick={() => step(-1)}>
            <ChevronLeft aria-hidden /> Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={index >= list.length - 1}
            onClick={() => step(1)}
          >
            Next <ChevronRight aria-hidden />
          </Button>
        </div>
      </div>

      <header className="flex flex-wrap items-center gap-4">
        <div
          role="img"
          aria-label={`${percent}% complete`}
          className="grid size-14 place-items-center rounded-full text-sm font-semibold"
          style={{
            background: `conic-gradient(var(--success) ${percent * 3.6}deg, var(--muted) 0)`,
          }}
        >
          <span className="grid size-10 place-items-center rounded-full bg-background">
            {percent}%
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold">{p.code}</h1>
          <p className="text-sm text-muted-foreground">
            {[p.group, p.cohort, p.enrolment_status].filter(Boolean).join(" · ")}
          </p>
        </div>
        {columns.length > 0 && (
          <p className="text-sm text-muted-foreground">
            {doneCount} of {columns.length} entries done
            {todo.length > 0 ? `, ${todo.length} to do` : ""}
          </p>
        )}
      </header>

      {canEdit && columns.length > 0 && (
        <ParticipantFiles
          labId={labId}
          projectId={projectId}
          participant={p}
          columns={columns}
          cellOf={cellOf}
          registry={registry}
        />
      )}

      {columns.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No data columns yet, so there is nothing to record here. Project leads add columns on the
          participants page.
        </p>
      )}

      {columns.length > 0 && todo.length === 0 && !showDone && (
        <p role="status" className="text-sm font-medium text-success-text">
          Everything for {p.code} is done.
        </p>
      )}

      {CATEGORIES.map(([cat, catLabel]) => {
        const inCat = columns.filter((c) => c.category === cat);
        if (!inCat.length) return null;
        const open = showDone ? inCat : inCat.filter((c) => !isDone(c.id));
        const finished = inCat.length - inCat.filter((c) => !isDone(c.id)).length;
        if (!open.length) return null;
        return (
          <section key={cat} aria-label={catLabel} className="grid gap-2">
            <h2 className="flex items-baseline gap-2 text-sm font-semibold">
              {catLabel}
              <span className="text-xs font-normal text-muted-foreground">
                {finished} of {inCat.length} done
              </span>
            </h2>
            <ul className="divide-y rounded-lg border bg-card">
              {open.map((c) => {
                const cell = cellOf(c.id);
                const reason = reasons.find((r) => r.id === cell?.reason)?.label;
                const files = cell?.files ?? [];
                return (
                  <li key={c.id} className="grid gap-1 px-3 py-2">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                      <span className="min-w-40 flex-1 font-medium">{c.name}</span>
                      <StatusChip status={statusOf(cell)} files={files.length} />
                      {canEdit && !isDone(c.id) && (
                        <Button
                          variant="outline"
                          size="sm"
                          aria-label={`Mark ${c.name} complete`}
                          onClick={() => markComplete(c.id, c.name)}
                        >
                          <Check aria-hidden /> Mark complete
                        </Button>
                      )}
                    </div>
                    {(reason || cell?.due_date || files.length > 0) && (
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-sm text-muted-foreground">
                        {reason && <span>{reason}</span>}
                        {cell?.due_date && <span>Due {cell.due_date}</span>}
                        {files.map((f) => (
                          <a
                            key={f.id}
                            href={f.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex max-w-56 items-center gap-1 text-foreground underline underline-offset-2"
                          >
                            <Paperclip aria-hidden className="size-3.5 shrink-0" />
                            <span className="truncate">{f.title || "Open file"}</span>
                          </a>
                        ))}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}

      {columns.length > 0 && doneCount > 0 && (
        <Button
          variant="ghost"
          size="sm"
          className="justify-self-start"
          aria-pressed={showDone}
          onClick={() => setShowDone((v) => !v)}
        >
          {showDone ? "Hide finished entries" : `Show ${doneCount} finished`}
        </Button>
      )}

      <Disclosure
        title="History"
        hint={events.length ? `${events.length} changes` : "No changes yet"}
      >
        <ul className="grid gap-1 text-sm">
          {events.map((e) => {
            const col = (registry.columns.data ?? []).find((c) => c.id === e.component);
            return (
              <li key={e.id} className="flex flex-wrap items-center gap-2">
                <span>{col ? col.name : e.action.replace("_", " ")}</span>
                {e.from_value && e.component && (
                  <StatusChip status={e.from_value as CellStatus} compact />
                )}
                {e.to_value && e.component && (
                  <StatusChip status={e.to_value as CellStatus} compact />
                )}
                <RelativeTime value={e.created_at} className="text-xs text-muted-foreground" />
              </li>
            );
          })}
        </ul>
      </Disclosure>
    </div>
  );
}
