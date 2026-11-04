import { FlaskConical } from "lucide-react";
import { Link, Navigate } from "react-router";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useLabs } from "@/hooks/workspace";
import { APP_NAME } from "@/lib/constants";
import { formErrors } from "@/lib/forms";
import { FormError } from "@/components/shared/FormError";

/** Landing page: first-run empty state when the user has no labs, otherwise straight into their first lab. */
export function HomePage() {
  const { data: labs, isLoading, error } = useLabs();
  if (isLoading)
    return (
      <div aria-busy="true" aria-label="Loading" className="grid gap-3">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  if (error) return <FormError message={formErrors(error, []).form} />;
  const first = labs?.[0];
  if (first) return <Navigate to={`/labs/${first.id}`} replace />;
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

export function NotBuiltPage() {
  return <EmptyState title="Nothing here yet" description="This section is coming soon." />;
}
