import { AlertTriangle, Printer } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { useHandover } from "@/hooks/handover";
import type { HandoverItem } from "@/lib/api-types";
import { personName } from "@/lib/api-types";
import { ApiError } from "@/lib/api";

const EMPTY: Record<string, string> = {
  open_tasks: "No open tasks are assigned to them.",
  unassigned_tasks: "No tasks were unassigned from them after an access change.",
  documents: "They have not created or last edited any documents.",
  analyses: "They have not run any analyses.",
  results: "None of their analyses have results.",
  datasets: "They do not control any datasets.",
  decisions: "They have not recorded any decisions.",
  ethics_approvals: "No ethics approvals are linked to projects they lead.",
  projects_led: "They do not lead any projects.",
};

function Items({ items, showReason = true }: { items: HandoverItem[]; showReason?: boolean }) {
  return (
    <ul className="grid divide-y rounded-lg border bg-background">
      {items.map((i) => (
        <li
          key={`${i.kind}-${i.id}`}
          className="flex flex-wrap items-baseline justify-between gap-x-4 px-3 py-2 text-sm"
        >
          <Link to={i.href} className="font-medium hover:underline">
            {i.title}
          </Link>
          <span className="text-xs text-muted-foreground">
            {[
              i.project?.name,
              showReason
                ? i.reason.replace(
                    /\(([a-z]+(?:_[a-z]+)*)\)$/,
                    (_, v: string) => `(${v === "todo" ? "to do" : v.replace(/_/g, " ")})`,
                  )
                : null,
            ]
              .filter(Boolean)
              .join(" | ")}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Handover report for a person, lab-wide (`/members/:membershipId/handover`) or for one
 * project (`/projects/:projectId/handover?user=<id>`). */
export function HandoverPage() {
  const { labId = "", membershipId, projectId } = useParams();
  const [search] = useSearchParams();
  const user = search.get("user");
  const path = membershipId
    ? `/api/labs/${labId}/members/${membershipId}/handover/`
    : `/api/labs/${labId}/projects/${projectId}/handover/${user ? `?user=${user}` : ""}`;
  const { data, isLoading, error } = useHandover(path);

  if (isLoading) return <p className="text-sm text-muted-foreground">Preparing the report...</p>;
  if (error || !data) {
    const denied = error instanceof ApiError && error.status === 403;
    return (
      <EmptyState
        title="Handover report unavailable"
        description={
          denied
            ? "You do not have permission to generate this report."
            : "We could not generate this report. Try again."
        }
      />
    );
  }
  const date = new Date(data.generated_at).toLocaleDateString(undefined, { dateStyle: "long" });
  const scope = data.project ? `Limited to ${data.project.name}.` : "Everything you can see.";
  return (
    <div className="grid gap-6">
      <PageHeader
        title={`Handover: ${personName({ display_name: data.person.display_name, email: data.person.email })}`}
        description={`Generated ${date}. ${scope}`}
        actions={
          <Button variant="outline" className="print:hidden" onClick={() => window.print()}>
            <Printer className="size-4" aria-hidden /> Print or save as PDF
          </Button>
        }
      />
      {data.no_other_owner.length > 0 && (
        <section
          aria-labelledby="no-other-owner"
          className="grid gap-3 rounded-lg border border-warning/30 bg-warning/10 p-4"
        >
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 size-5 text-warning" aria-hidden />
            <div>
              <h2 id="no-other-owner" className="text-base font-semibold">
                No other owner ({data.no_other_owner.length})
              </h2>
              <p className="text-sm text-muted-foreground">
                These items need a new owner before this person leaves.
              </p>
            </div>
          </div>
          <Items items={data.no_other_owner} />
        </section>
      )}
      {data.sections.map((s) => (
        <section key={s.key} aria-labelledby={`h-${s.key}`} className="grid gap-3">
          <h2 id={`h-${s.key}`} className="text-base font-semibold">
            {s.label} ({s.items.length})
          </h2>
          {s.items.length ? (
            <Items items={s.items} />
          ) : (
            <EmptyState
              className="py-6"
              title={`No ${s.label.toLowerCase()}`}
              description={EMPTY[s.key] ?? "Nothing to hand over."}
            />
          )}
        </section>
      ))}
    </div>
  );
}
