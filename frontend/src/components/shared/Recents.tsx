import { FileText, FlaskConical, FolderKanban, ShieldCheck } from "lucide-react";
import { Link } from "react-router";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { useRecents } from "@/hooks/preferences";
import type { RecentKind } from "@/lib/pins";

const ICONS = {
  project: FolderKanban,
  document: FileText,
  record: FlaskConical,
  approval: ShieldCheck,
} satisfies Record<RecentKind, unknown>;

/** What the user opened lately. Nothing to show means no section at all, not an empty one. */
export function Recents() {
  const recents = useRecents();
  if (recents.length === 0) return null;
  return (
    <section aria-labelledby="recents" className="mb-8 grid gap-3">
      <h2 id="recents" className="text-base font-semibold">
        Recent
      </h2>
      <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {recents.map((r) => {
          const Icon = ICONS[r.kind];
          return (
            <li key={r.url}>
              <Link
                to={r.url}
                className="flex items-center gap-3 rounded-md border p-3 text-sm hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="min-w-0 flex-1 truncate font-medium">{r.label}</span>
                <RelativeTime value={r.at} className="shrink-0 text-xs text-muted-foreground" />
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
