import { Link } from "react-router";
import { useProjects } from "@/hooks/projects";

/** The projects this person is on, so a new member has somewhere to go on day one. */
export function YourProjects({ labId }: { labId: string }) {
  const { data } = useProjects(labId);
  if (!data) return null;
  const projects = data.filter((p) => p.status !== "archived");
  return (
    <section aria-labelledby="your-projects" className="mt-6 grid gap-2">
      <div className="flex items-center justify-between gap-2">
        <h2 id="your-projects" className="text-base font-medium">
          Your projects
        </h2>
        {projects.length > 0 && (
          <Link
            to={`/labs/${labId}/projects`}
            className="text-sm text-primary underline-offset-2 hover:underline"
          >
            All projects →
          </Link>
        )}
      </div>
      {projects.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          You are not on a project yet. Ask a PI or lab admin to add you to one.
        </p>
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2">
          {projects.slice(0, 6).map((p) => (
            <li key={p.id}>
              <Link
                to={`/labs/${labId}/projects/${p.id}`}
                className="block truncate rounded-md border p-3 text-sm font-medium hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                {p.name}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
