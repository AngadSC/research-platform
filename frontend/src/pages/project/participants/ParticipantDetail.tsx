import { Link } from "react-router";
import type { RegistryCell, RegistryColumn, RegistryParticipant } from "@/lib/api-types";
import { STATUS, statusOf } from "@/lib/participants";

/** The quiet second level of a participant row: what is attached to each cell, one line each. */
export function ParticipantDetail({
  participant,
  columns,
  cellOf,
  href,
}: {
  participant: RegistryParticipant;
  columns: RegistryColumn[];
  cellOf: (c: RegistryColumn) => RegistryCell | undefined;
  href: string;
}) {
  const meta = [participant.group, participant.cohort].filter(Boolean).join(" · ");
  const withFiles = columns.filter((c) => (cellOf(c)?.files.length ?? 0) > 0);
  return (
    <div className="grid gap-1">
      <p className="text-muted-foreground">
        {meta || "No group or cohort"}
        {" · "}
        <Link className="underline-offset-2 hover:underline" to={href}>
          Open full page
        </Link>
      </p>
      {withFiles.length === 0 ? (
        <p className="text-muted-foreground">No files linked yet.</p>
      ) : (
        <ul className="grid gap-0.5">
          {withFiles.map((c) => {
            const cell = cellOf(c)!;
            return (
              <li key={c.id} className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-medium">{c.name}</span>
                <span className="text-xs text-muted-foreground">
                  {STATUS[statusOf(cell)].label}
                </span>
                {cell.files.map((f) => (
                  <a
                    key={f.id}
                    href={f.url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="underline-offset-2 hover:underline"
                  >
                    {f.title || "Open file"}
                  </a>
                ))}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
