import { Outlet } from "react-router";
import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { Toaster } from "@/components/ui/sonner";
import { useCrumbs } from "@/hooks/crumbs";
import { APP_NAME } from "@/lib/constants";

/** Plain centred layout for pages people see before they are signed in. */
export function AuthLayout() {
  const crumbs = useCrumbs();
  return (
    <div className="flex min-h-screen flex-col items-center bg-background px-4 py-12 text-foreground">
      <div className="grid w-full max-w-md gap-6">
        <p className="text-sm font-semibold">{APP_NAME}</p>
        <Breadcrumbs items={crumbs} />
        <main className="rounded-lg border p-6">
          <Outlet />
        </main>
      </div>
      <Toaster />
    </div>
  );
}
