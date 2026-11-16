import { Users } from "lucide-react";
import { Link, useParams } from "react-router";
import { EmptyState, GettingStartedLink } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { useLabOverview } from "@/hooks/participants";
import { StatusChip } from "@/pages/project/participants/StatusChip";
import { CODES_ONLY } from "@/lib/participants";

/** A read-only roll-up of every project's participant data you can see. */
export function ParticipantsOverviewPage() {
  const { labId = "" } = useParams();
  const { data, isLoading } = useLabOverview(labId);
  const to = (project: string, q = "") => `/labs/${labId}/projects/${project}/participants${q}`;
  return (
    <>
      <PageHeader
        title="Participants"
        description={`Who has what, across your projects. ${CODES_ONLY}`}
      />
      {isLoading && <Skeleton aria-label="Loading" className="h-40" />}
      {data && data.projects.length === 0 && (
        <EmptyState
          icon={Users}
          title="No participant data yet"
          description="Open a project, choose Participants, and add your first participants or import a sheet."
          footer={<GettingStartedLink labId={labId} />}
          why="Once participants are added, you can see what is missing and what is overdue across every project."
        />
      )}
      {data && data.projects.length > 0 && (
        <div className="grid gap-8">
          <section aria-label="Projects" className="grid gap-2">
            <h2 className="text-base font-semibold">Projects</h2>
            <ul className="divide-y rounded-lg border">
              {data.projects.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm">
                  <Link
                    to={to(p.id)}
                    className="min-w-40 flex-1 font-medium underline-offset-2 hover:underline"
                  >
                    {p.name}
                  </Link>
                  <span>{p.participants} participants</span>
                  <span>{p.percent}% complete</span>
                  <Link
                    to={to(p.id, "?status=missing")}
                    className="underline-offset-2 hover:underline"
                  >
                    {p.missing} missing
                  </Link>
                  <Link to={to(p.id, "?overdue=1")} className="underline-offset-2 hover:underline">
                    {p.overdue} overdue
                  </Link>
                  <Link
                    to={to(p.id, "?status=needs_review")}
                    className="underline-offset-2 hover:underline"
                  >
                    {p.needs_review} to review
                  </Link>
                </li>
              ))}
            </ul>
          </section>
          <section aria-label="By column" className="grid gap-2">
            <h2 className="text-base font-semibold">Completeness by column</h2>
            <ul className="grid gap-2">
              {data.by_component.map((c) => (
                <li
                  key={c.name}
                  className="grid grid-cols-[10rem_1fr_3rem] items-center gap-2 text-sm"
                >
                  <span className="truncate">{c.name}</span>
                  <div
                    role="img"
                    aria-label={`${c.name}: ${c.percent}% complete`}
                    className="h-2 overflow-hidden rounded-full bg-muted"
                  >
                    <div className="h-full bg-success" style={{ width: `${c.percent}%` }} />
                  </div>
                  <span className="text-right text-muted-foreground">{c.percent}%</span>
                </li>
              ))}
            </ul>
          </section>
          <div className="grid gap-6 md:grid-cols-2">
            <section aria-label="Missing by reason" className="grid gap-2">
              <h2 className="text-base font-semibold">Missing, and why</h2>
              {data.missing_by_reason.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nothing is marked missing.</p>
              ) : (
                <ul className="text-sm">
                  {data.missing_by_reason.map((r) => (
                    <li key={r.reason} className="flex justify-between border-b py-1">
                      <span>{r.reason}</span>
                      <span>{r.count}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section aria-label="Translations pending" className="grid gap-2">
              <h2 className="text-base font-semibold">Translations pending, by language</h2>
              {data.translation_pending.length === 0 ? (
                <p className="text-sm text-muted-foreground">No translations are waiting.</p>
              ) : (
                <ul className="text-sm">
                  {data.translation_pending.map((r) => (
                    <li key={r.group} className="flex justify-between border-b py-1">
                      <span>{r.group}</span>
                      <span>{r.count}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
          <section aria-label="Recently changed" className="grid gap-2">
            <h2 className="text-base font-semibold">Recently changed</h2>
            <ul className="text-sm">
              {data.recent.map((m) => (
                <li
                  key={`${m.participant_id}-${m.component}-${m.at}`}
                  className="flex items-center gap-2 border-b py-1"
                >
                  <Link
                    to={to(m.project)}
                    className="flex-1 truncate underline-offset-2 hover:underline"
                  >
                    {m.project_name}: {m.participant}, {m.component}
                  </Link>
                  <StatusChip status={m.status} compact />
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </>
  );
}
