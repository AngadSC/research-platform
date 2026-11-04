import { lazy, Suspense } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import type { ProjectTabProps } from "@/pages/ProjectPage";

// Lazy so React Flow stays out of the main bundle.
const Tab = lazy(() => import("@/pages/project/LineageTab"));

export function LazyLineageTab(props: ProjectTabProps) {
  return (
    <Suspense fallback={<Skeleton aria-label="Loading lineage" className="h-80" />}>
      <Tab {...props} />
    </Suspense>
  );
}
