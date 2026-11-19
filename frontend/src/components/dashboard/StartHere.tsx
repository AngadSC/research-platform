import { ArrowDown, ArrowUp, FileText, PinOff } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { usePinForEveryone, useStartHere } from "@/hooks/startHere";
import type { StartHerePin } from "@/lib/api-types";

const docPath = (labId: string, p: StartHerePin) =>
  p.project
    ? `/labs/${labId}/projects/${p.project}/documents/${p.id}`
    : `/labs/${labId}/documents/${p.id}`;

/** What the lab wants everyone to read first (D351). Nothing is shown when nothing is pinned.
 *  `labOnly` is for the top of Lab documents, which has no project documents. */
export function StartHere({
  labId,
  labOnly = false,
  canPin = false,
}: {
  labId: string;
  labOnly?: boolean;
  /** Can pin lab documents: sees a hint when nothing is pinned yet. */
  canPin?: boolean;
}) {
  const { data } = useStartHere(labId);
  const change = usePinForEveryone(labId);
  const [editing, setEditing] = useState(false);
  const [removing, setRemoving] = useState<StartHerePin | null>(null);
  const pins = (data ?? []).filter((p) => !labOnly || !p.project);
  if (pins.length === 0)
    return canPin && data ? (
      <p className="text-sm text-muted-foreground">
        Nothing is pinned yet. Pin a document for everyone from its ... menu.
      </p>
    ) : null;
  const canManage = pins.some((p) => p.can_manage);
  const run = (id: string, action: "unpin" | "up" | "down") => change.mutate({ id, action });
  return (
    <section aria-labelledby="start-here" className="grid gap-2 rounded-lg border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 id="start-here" className="text-base font-medium">
          Start here
        </h2>
        {canManage && (
          <Button
            variant="ghost"
            size="sm"
            aria-pressed={editing}
            onClick={() => setEditing((v) => !v)}
          >
            {editing ? "Done" : "Edit"}
          </Button>
        )}
      </div>
      <p className="-mt-1 text-xs text-muted-foreground">
        {pins.some((p) => p.project)
          ? "Lab documents show on everyone's Home. Project documents show to everyone in that project."
          : "Shown on everyone's Home"}
      </p>
      <ul className="grid gap-1 text-sm">
        {pins.map((p, i) => (
          <li key={p.id} className="flex items-center gap-2">
            <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            <Link
              to={docPath(labId, p)}
              className="min-w-0 flex-1 truncate font-medium underline-offset-2 hover:underline"
            >
              {p.title}
              {p.project_name && (
                <span className="font-normal text-muted-foreground"> · {p.project_name}</span>
              )}
            </Link>
            {editing && p.can_manage && (
              <span className="flex shrink-0">
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Move ${p.title} up`}
                  disabled={i === 0 || pins[i - 1]!.project !== p.project}
                  onClick={() => run(p.id, "up")}
                >
                  <ArrowUp aria-hidden />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Move ${p.title} down`}
                  disabled={i === pins.length - 1 || pins[i + 1]!.project !== p.project}
                  onClick={() => run(p.id, "down")}
                >
                  <ArrowDown aria-hidden />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Unpin ${p.title} for everyone`}
                  onClick={() => setRemoving(p)}
                >
                  <PinOff aria-hidden />
                </Button>
              </span>
            )}
          </li>
        ))}
      </ul>
      <Dialog open={!!removing} onOpenChange={(o) => !o && setRemoving(null)}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">
            Unpin {removing?.title} for everyone?
          </DialogTitle>
          <DialogDescription>
            It stays in its place in the lab. It just leaves this list.
          </DialogDescription>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setRemoving(null)}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                if (removing) run(removing.id, "unpin");
                setRemoving(null);
              }}
            >
              Unpin
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}
