import { ArrowDown, ArrowUp, FileText, PinOff } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { usePinForEveryone, useStartHere } from "@/hooks/startHere";
import type { StartHerePin } from "@/lib/api-types";

const docPath = (labId: string, p: StartHerePin) =>
  p.project
    ? `/labs/${labId}/projects/${p.project}/documents/${p.id}`
    : `/labs/${labId}/documents/${p.id}`;

/** What the lab wants everyone to read first (D346). Nothing is shown when nothing is pinned.
 *  `labOnly` is for the top of Lab documents, which has no project documents. */
export function StartHere({ labId, labOnly = false }: { labId: string; labOnly?: boolean }) {
  const { data } = useStartHere(labId);
  const change = usePinForEveryone(labId);
  const [editing, setEditing] = useState(false);
  const pins = (data ?? []).filter((p) => !labOnly || !p.project);
  if (pins.length === 0) return null;
  const canManage = pins.some((p) => p.can_manage);
  const run = (id: string, action: "unpin" | "up" | "down") =>
    change.mutate({ id, action }, { onError: () => toast.error("Could not change that.") });
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
                  onClick={() => run(p.id, "unpin")}
                >
                  <PinOff aria-hidden />
                </Button>
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
