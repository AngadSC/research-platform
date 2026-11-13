import { FlaskConical } from "lucide-react";
import { Link, Navigate } from "react-router";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCurrentLabId } from "@/hooks/crumbs";
import { useLabs } from "@/hooks/workspace";
import { roleLabel } from "@/lib/api-types";
import { APP_NAME } from "@/lib/constants";
import { formErrors } from "@/lib/forms";
import { FormError } from "@/components/shared/FormError";

/** Landing page: first-run empty state when the user has no labs, otherwise straight into their current lab. */
export function HomePage() {
  const { isLoading, error } = useLabs();
  const labId = useCurrentLabId();
  if (isLoading)
    return (
      <div aria-busy="true" aria-label="Loading" className="grid gap-3">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  if (error) return <FormError message={formErrors(error, []).form} />;
  if (labId) return <Navigate to={`/labs/${labId}`} replace />;
  return (
    <>
      <PageHeader
        title={`Welcome to ${APP_NAME}`}
        description="Your projects, datasets and results in one place."
      />
      <EmptyState
        icon={FlaskConical}
        title="Create your first lab"
        description="A lab is where your team, projects and results live. Create one, or ask a colleague to invite you to theirs."
        action={
          <Button asChild>
            <Link to="/labs/new">Create a lab</Link>
          </Button>
        }
      />
    </>
  );
}

/** Every lab you belong to, and a way to add one. With none, the first-run page says what to do. */
export function LabListPage() {
  const { data: labs, error } = useLabs();
  if (error) return <FormError message={formErrors(error, []).form} />;
  if (labs?.length === 0) return <Navigate to="/" replace />;
  return (
    <>
      <PageHeader
        title="Labs"
        description="Pick a lab to open it."
        actions={
          <Button asChild>
            <Link to="/labs/new">Create a lab</Link>
          </Button>
        }
      />
      {!labs ? (
        <Skeleton aria-label="Loading" className="h-40 w-full" />
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2">
          {labs.map((lab) => (
            <li key={lab.id}>
              <Link
                to={`/labs/${lab.id}`}
                className="block rounded-md border p-3 hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                <span className="font-medium">{lab.name}</span>
                <span className="block text-xs text-muted-foreground">
                  {lab.institution.name} · You are {roleLabel(lab.my_role ?? "")}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export function NotFoundPage() {
  const labId = useCurrentLabId();
  const lab = useLabs().data?.find((l) => l.id === labId);
  return (
    <EmptyState
      title="Page not found"
      description="This address doesn't match a page. Check the link, or go back to your lab."
      action={
        <Button asChild variant="outline">
          <Link to={lab ? `/labs/${lab.id}` : "/"}>{lab ? `Back to ${lab.name}` : "Go home"}</Link>
        </Button>
      }
    />
  );
}
