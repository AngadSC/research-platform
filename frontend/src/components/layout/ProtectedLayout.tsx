import { Navigate, useLocation } from "react-router";
import { AppShell } from "@/components/layout/AppShell";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/hooks/auth";

/** Sends signed-out visitors to /login and brings them back afterwards. */
export function ProtectedLayout() {
  const { isLoading, isAuthenticated } = useAuth();
  const { pathname, search } = useLocation();
  if (isLoading)
    return (
      <div className="grid gap-3 p-8" aria-busy="true" aria-label="Loading">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-4 w-80" />
      </div>
    );
  if (!isAuthenticated)
    return <Navigate to={`/login?next=${encodeURIComponent(pathname + search)}`} replace />;
  return <AppShell />;
}
