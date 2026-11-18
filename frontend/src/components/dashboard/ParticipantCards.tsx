import { Link } from "react-router";
import { StatusChip } from "@/pages/project/participants/StatusChip";
import { useLabOverview } from "@/hooks/participants";
import { cn } from "@/lib/utils";

const at = (labId: string, project: string, query = "") =>
  `/labs/${labId}/projects/${project}/participants${query}`;

/**
 * Participant data at a glance: what is missing, what is overdue, and what is waiting on you.
 * Hidden until a project has participants. Every item opens the grid already filtered.
 */
export function ParticipantCards({
  labId,
  compact = false,
}: {
  labId: string;
  /** Only "waiting on me", for My work. */
  compact?: boolean;
}) {
  const { data } = useLabOverview(labId);
  if (!data || data.projects.length === 0) return null;
  const mine = data.waiting_on_me;
  const missing = data.projects.reduce((n, p) => n + p.missing, 0);
  const overdue = data.projects.reduce((n, p) => n + p.overdue, 0);
  const first = data.projects[0]!;
  const percentsAllZero = data.projects.every((p) => p.percent === 0);

  const waiting = (
    <section aria-label="Waiting on me" className="glass rounded-2xl p-4">
      <h2 className="text-sm font-semibold">Participant data waiting on you</h2>
      {mine.length === 0 ? (
        <p className="mt-2 text-sm text-muted-foreground">
          All caught up. Nothing is waiting on you.
        </p>
      ) : (
        <ul className="mt-2 grid gap-1 text-sm">
          {mine.slice(0, compact ? 8 : 5).map((m) => (
            <li key={`${m.participant_id}-${m.component}`} className="flex items-center gap-2">
              <Link
                to={at(labId, m.project, `?owner=me`)}
                className="min-w-0 flex-1 truncate underline-offset-2 hover:underline"
              >
                {m.participant}, {m.component}
              </Link>
              {m.due_date && <span className="text-xs text-muted-foreground">{m.due_date}</span>}
              <StatusChip status={m.status} compact />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
  if (compact) return mine.length > 0 ? waiting : null;
  if (percentsAllZero && missing === 0 && overdue === 0 && mine.length === 0)
    return (
      <section aria-label="Participant data" className="glass rounded-2xl p-4">
        <h2 className="text-sm font-semibold">Participant data</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Not started yet. Add participants by code (like P-001) in a project, then list the data
          each one should have, and this card shows who is missing what.
        </p>
        <Link
          to={`/labs/${labId}/participants`}
          className="mt-2 inline-block text-sm font-medium text-primary underline-offset-2 hover:underline"
        >
          Set up participants →
        </Link>
      </section>
    );
  return (
    <div
      className={cn("grid gap-3", mine.length > 0 ? "lg:grid-cols-3" : "lg:grid-cols-2")}
      aria-label="Participant data"
    >
      <section aria-label="Completeness" className="glass rounded-2xl p-4">
        <h2 className="text-sm font-semibold">Participant data</h2>
        <ul className="mt-2 grid gap-2 text-sm">
          {data.projects.slice(0, 4).map((p) => (
            <li key={p.id}>
              <Link to={at(labId, p.id)} className="flex items-center justify-between gap-2">
                <span className="truncate">{p.name}</span>
                <span className="text-muted-foreground">
                  {p.percent === 0 ? "Not started" : `${p.percent}%`}
                </span>
              </Link>
              <div
                role="img"
                aria-label={p.percent === 0 ? "Not started" : `${p.percent}% complete`}
                className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted"
              >
                <div className="h-full bg-success" style={{ width: `${p.percent}%` }} />
              </div>
            </li>
          ))}
        </ul>
        <Link
          to={`/labs/${labId}/participants`}
          className="mt-3 inline-block text-sm underline-offset-2 hover:underline"
        >
          All projects
        </Link>
      </section>
      <section aria-label="Participant data gaps" className="glass rounded-2xl p-4">
        <h2 className="text-sm font-semibold">Missing participant data</h2>
        <ul className="mt-2 grid grid-cols-2 gap-2">
          <li>
            <Link
              to={at(labId, first.id, "?status=missing")}
              className={cn("block rounded-lg border p-2 hover:bg-muted")}
            >
              <span className="block text-xl font-semibold">{missing}</span>
              <span className="text-xs text-muted-foreground">Missing</span>
            </Link>
          </li>
          <li>
            <Link
              to={at(labId, first.id, "?overdue=1")}
              className="block rounded-lg border p-2 hover:bg-muted"
            >
              <span className="block text-xl font-semibold">{overdue}</span>
              <span className="text-xs text-muted-foreground">Overdue</span>
            </Link>
          </li>
        </ul>
        {data.missing_by_reason.length > 0 && (
          <ul className="mt-3 grid gap-0.5 text-sm text-muted-foreground">
            {data.missing_by_reason.slice(0, 4).map((r) => (
              <li key={r.reason} className="flex justify-between">
                <span>{r.reason}</span>
                <span>{r.count}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      {mine.length > 0 && waiting}
    </div>
  );
}
