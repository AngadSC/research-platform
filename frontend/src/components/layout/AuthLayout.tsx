import { Outlet } from "react-router";
import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { Toaster } from "@/components/ui/sonner";
import { useCrumbs } from "@/hooks/crumbs";
import { BrandMark } from "./BrandMark";

/** Plain centred layout for pages people see before they are signed in. */
export function AuthLayout() {
  const crumbs = useCrumbs();
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="sidebar-scope h-52 px-4 pt-12">
        <div className="mx-auto grid w-full max-w-md gap-3">
          <BrandMark />
          <Breadcrumbs items={crumbs} />
        </div>
      </div>
      <div className="px-4 pb-12">
        <main className="mx-auto -mt-24 w-full max-w-md rounded-lg border bg-card p-6 text-card-foreground">
          <Outlet />
        </main>
      </div>
      <Toaster />
    </div>
  );
}
