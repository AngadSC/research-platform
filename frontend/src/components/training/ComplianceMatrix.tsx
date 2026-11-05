import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { TrainingCompliance } from "@/lib/api-types";
import { dayText } from "@/lib/ethics";
import { STATUS } from "@/lib/training";

export function StatusPill({ status }: { status: keyof typeof STATUS }) {
  const s = STATUS[status];
  return <Badge variant={s.tone}>{s.label}</Badge>;
}

/** Members by required trainings (D177). `onVerify` shows a Verify button on unverified records. */
export function ComplianceMatrix({
  data,
  onVerify,
}: {
  data: TrainingCompliance;
  onVerify?: (recordId: string) => void;
}) {
  const { requirements, members, summary } = data;
  if (requirements.length === 0 || members.length === 0)
    return <p className="text-sm text-muted-foreground">No required trainings yet.</p>;
  return (
    <div className="grid gap-2">
      <p className="text-sm text-muted-foreground" aria-label="Compliance summary">
        {summary.done} done, {summary.expiring} expiring within 60 days, {summary.expired} expired,{" "}
        {summary.missing} missing
      </p>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/40 text-left">
              <th scope="col" className="px-3 py-2 font-medium">
                Member
              </th>
              {requirements.map((r) => (
                <th key={r.id} scope="col" className="px-3 py-2 font-medium">
                  {r.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.user.id} className="border-b last:border-0">
                <th scope="row" className="px-3 py-2 text-left font-medium">
                  {m.user.display_name || m.user.email}
                </th>
                {requirements.map((r) => {
                  const cell = m.cells[r.id];
                  if (!cell)
                    return (
                      <td
                        key={r.id}
                        className="px-3 py-2 text-muted-foreground"
                        aria-label="Not required"
                      >
                        <span aria-hidden="true">-</span>
                      </td>
                    );
                  return (
                    <td key={r.id} className="px-3 py-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusPill status={cell.status} />
                        {cell.expires_on && (
                          <span className="text-xs text-muted-foreground">
                            {cell.status === "expired" ? "expired" : "expires"}{" "}
                            {dayText(cell.expires_on)}
                          </span>
                        )}
                        {cell.record && !cell.verified && (
                          <span className="text-xs text-muted-foreground">Not verified</span>
                        )}
                        {cell.record && !cell.verified && onVerify && (
                          <Button
                            variant="outline"
                            size="sm"
                            aria-label={`Verify ${r.name} for ${m.user.display_name || m.user.email}`}
                            onClick={() => onVerify(cell.record!)}
                          >
                            Verify
                          </Button>
                        )}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
