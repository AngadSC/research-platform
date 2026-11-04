import { lazy, Suspense } from "react";

// Lazy so BlockNote stays out of the main bundle.
const Page = lazy(() => import("@/pages/DocumentPage"));

export function DocumentPage() {
  return (
    <Suspense fallback={null}>
      <Page />
    </Suspense>
  );
}
