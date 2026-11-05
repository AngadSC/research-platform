import { Outlet, useLocation } from "react-router";
import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { Toaster } from "@/components/ui/sonner";
import { useCrumbs } from "@/hooks/crumbs";
import { Features, HeroText, LandingHeader } from "@/pages/LandingPage";

/** Signed-out layout. Sign in and Register also show the product page around the form. */
export function AuthLayout() {
  const crumbs = useCrumbs();
  const { pathname } = useLocation();
  const landing = pathname === "/login" || pathname === "/signup";
  return (
    <div className="min-h-screen bg-background text-foreground">
      <LandingHeader />
      <div className="mx-auto grid max-w-5xl gap-16 px-4 py-10 md:px-8">
        <div
          className={
            landing ? "grid items-center gap-10 lg:grid-cols-2" : "mx-auto w-full max-w-md"
          }
        >
          {landing && <HeroText />}
          <div className="grid w-full max-w-md gap-4 justify-self-center lg:justify-self-end">
            {!landing && <Breadcrumbs items={crumbs} />}
            <main className="rounded-xl bg-muted p-6">
              <Outlet />
            </main>
          </div>
        </div>
        {landing && <Features />}
      </div>
      <Toaster />
    </div>
  );
}
