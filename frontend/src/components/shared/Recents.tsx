import { FileText, FlaskConical, FolderKanban, ShieldCheck } from "lucide-react";
import { Link } from "react-router";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { useCurrentLabId } from "@/hooks/crumbs";
import { useRecents } from "@/hooks/preferences";
import { useProjects } from "@/hooks/projects";
import type { RecentKind } from "@/lib/pins";
import { projectColorStyle } from "@/lib/projectColors";

const ICONS = {
  project: FolderKanban,
  document: FileText,
  record: FlaskConical,
  approval: ShieldCheck,
} satisfies Record<RecentKind, unknown>;

const KIND_LABEL: Record<RecentKind, string> = {
  project: "Project",
  document: "Document",
  record: "Record",
  approval: "Ethics approval",
};

/** How many show. Twelve identical cards read as noise; the rest stay in the palette and history. */
const SHOWN = 6;

const PROJECT_IN_URL = /^\/labs\/[^/]+\/projects\/([^/?#]+)/;

/** What the user opened lately. Nothing to show means no section at all, not an empty one. Each
 * item takes its project's colour, so a project is recognisable at a glance. */
export function Recents() {
  const recents = useRecents().slice(0, SHOWN);
  const { data: projects = [] } = useProjects(useCurrentLabId());
  if (recents.length === 0) return null;
  return (
    <section aria-labelledby="recents" className="mb-8 grid gap-3">
      <h2 id="recents" className="text-base font-semibold">
        Recent
      </h2>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {recents.map((r, i) => {
          const Icon = ICONS[r.kind];
          const project = projects.find((p) => p.id === PROJECT_IN_URL.exec(r.url)?.[1]);
          return (
            <li
              key={r.url}
              className={i >= 4 ? "hidden sm:block" : undefined}
              style={project ? projectColorStyle(project.color) : undefined}
            >
              <Link
                to={r.url}
                className="flex items-start gap-3 rounded-lg border p-3 text-sm hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                <span
                  aria-hidden
                  className={
                    project
                      ? "grid size-8 shrink-0 place-items-center rounded-md bg-[color-mix(in_srgb,var(--project)_18%,transparent)] text-(--project)"
                      : "grid size-8 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground"
                  }
                >
                  <Icon className="size-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block font-medium break-words">{r.label}</span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">
                    {r.kind === "project"
                      ? KIND_LABEL.project
                      : (project?.name ?? KIND_LABEL[r.kind])}
                    {" · "}
                    <RelativeTime value={r.at} />
                  </span>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
