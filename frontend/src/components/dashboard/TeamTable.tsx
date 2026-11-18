import { Link } from "react-router";
import { RelativeTime } from "@/components/shared/RelativeTime";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { DashPerson } from "@/hooks/dashboard";
import { roleLabel, type TrainingCompliance } from "@/lib/api-types";
import { cn } from "@/lib/utils";

const NEEDS_ATTENTION = ["expired", "expiring", "missing"];

/**
 * Home, "Team" (PIs and lab admins): one row per member. Counts come from the dashboard and open
 * the matching tasks; training is the same data as the Training page; "last active" is the lab's
 * audit log, so it is blank for someone who has done nothing yet.
 */
export function TeamTable({
  labId,
  people,
  training,
}: {
  labId: string;
  people: DashPerson[];
  /** The Training page's data, which Home already loads; undefined until it arrives or if it fails. */
  training?: TrainingCompliance;
}) {
  const attention = new Map(
    (training?.members ?? []).map((m) => [
      m.user.id,
      training!.requirements.filter((r) => NEEDS_ATTENTION.includes(m.cells[r.id]?.status ?? ""))
        .length,
    ]),
  );
  const rows = [...people].sort(
    (a, b) => b.overdue_tasks - a.overdue_tasks || a.name.localeCompare(b.name),
  );
  const tasks = (p: DashPerson, show: string, n: number, danger = false) =>
    n === 0 ? (
      <span className="text-muted-foreground">0</span>
    ) : (
      <Link
        to={`/labs/${labId}/team-tasks?assignee=${p.user_id}&show=${show}`}
        aria-label={`${n} ${show.replace("_", " ")} tasks for ${p.name}`}
        className={cn(
          "underline-offset-2 hover:underline",
          danger && "font-semibold text-danger-text",
        )}
      >
        {n}
      </Link>
    );
  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>Member</TableHead>
            <TableHead>Role</TableHead>
            <TableHead className="text-right">Overdue</TableHead>
            <TableHead className="text-right">In progress</TableHead>
            <TableHead className="text-right">Open</TableHead>
            <TableHead className="text-right">Done in 30 days</TableHead>
            <TableHead>Training</TableHead>
            <TableHead>Last active</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((p) => {
            const n = attention.get(p.user_id);
            return (
              <TableRow key={p.user_id}>
                <TableCell className="font-medium">{p.name}</TableCell>
                <TableCell>{roleLabel(p.role)}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {tasks(p, "overdue", p.overdue_tasks, true)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {tasks(p, "in_progress", p.in_progress_tasks)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {tasks(p, "open", p.open_tasks)}
                </TableCell>
                <TableCell className="text-right tabular-nums">{p.done_last_30_days}</TableCell>
                <TableCell>
                  {n === undefined ? (
                    <span className="text-muted-foreground">-</span>
                  ) : n > 0 ? (
                    <Link
                      to={`/labs/${labId}/training`}
                      className="font-medium text-danger-text underline-offset-2 hover:underline"
                    >
                      Needs attention
                    </Link>
                  ) : (
                    <span className="text-muted-foreground">OK</span>
                  )}
                </TableCell>
                <TableCell>
                  {p.last_active_at ? (
                    <RelativeTime value={p.last_active_at} />
                  ) : (
                    <span className="text-muted-foreground">No activity yet</span>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
