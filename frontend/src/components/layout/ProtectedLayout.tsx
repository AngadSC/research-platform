import { useEffect } from "react";
import { Navigate, useLocation } from "react-router";
import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/hooks/auth";
import { useMe } from "@/hooks/workspace";
import { identifyUser } from "@/lib/analytics";
import { LandingPage } from "@/pages/LandingPage";

/** Sends signed-out visitors to /login and brings them back afterwards. */
export function ProtectedLayout() {
  const { isLoading, isAuthenticated, unavailable, retry } = useAuth();
  const { pathname, search, hash } = useLocation();
  if (isLoading)
    return (
      <div className="grid gap-3 p-8" aria-busy="true" aria-label="Loading">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-4 w-80" />
      </div>
    );
  if (unavailable)
    return (
      <div role="status" className="grid max-w-md justify-items-start gap-3 p-8">
        <h1 className="text-lg font-semibold">labbenchos is briefly unavailable</h1>
        <p className="text-sm text-muted-foreground">
          This usually takes a minute, for example while we update. Your work is safe. We are
          retrying…
        </p>
        <Button variant="outline" onClick={retry}>
          Try again now
        </Button>
      </div>
    );
  if (!isAuthenticated && pathname === "/") return <LandingPage />;
  if (!isAuthenticated)
    return <Navigate to={`/login?next=${encodeURIComponent(pathname + search + hash)}`} replace />;
  return (
    <>
      <AnalyticsIdentity />
      <AppShell />
    </>
  );
}

/** D380: ties visits to a random account id, and leaves test and staff accounts out. */
function AnalyticsIdentity() {
  const me = useMe().data as { id?: string; email?: string; is_staff?: boolean } | undefined;
  useEffect(() => identifyUser(me), [me]);
  return null;
}
