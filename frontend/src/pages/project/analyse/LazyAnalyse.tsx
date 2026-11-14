import { lazy, Suspense } from "react";
import type { ProjectTabProps } from "@/pages/ProjectPage";

// The statistics screens (and their charts) stay out of the main bundle until opened.
const AnalysePage = lazy(() => import("@/pages/project/analyse/AnalysePage"));

export default function LazyAnalyse(props: ProjectTabProps) {
  return (
    <Suspense fallback={<p aria-busy="true">Loading statistics</p>}>
      <AnalysePage {...props} />
    </Suspense>
  );
}
