import { Check, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DataIssue, LoadOptions } from "@/lib/stats/contract";

/** What the engine noticed in the file, each with its fix (or an Undo for one already applied). */
export function DataIssues({
  issues,
  busy,
  onFix,
}: {
  issues: DataIssue[];
  busy: boolean;
  onFix: (fix: LoadOptions) => void;
}) {
  if (!issues.length) return null;
  return (
    <section aria-label="Check this file" className="grid max-w-3xl gap-2 rounded-md border p-3">
      <h3 className="text-sm font-medium">Check this file</h3>
      <ul className="grid gap-2">
        {issues.map((issue) => (
          <li key={issue.id} className="flex flex-wrap items-start gap-x-3 gap-y-1 text-sm">
            {issue.applied ? (
              <Check aria-label="Fixed" className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            ) : (
              <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            )}
            <span className="min-w-0 flex-1">{issue.message}</span>
            {issue.fix && (
              <Button size="sm" variant="outline" disabled={busy} onClick={() => onFix(issue.fix!)}>
                {issue.applied ? "Undo" : issue.action}
              </Button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
