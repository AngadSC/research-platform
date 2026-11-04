import { lazy, Suspense } from "react";

// pdf.js stays out of the main bundle until a file is opened.
const PdfViewerPage = lazy(() => import("@/pages/project/PdfViewerPage"));

export default function PdfViewerRoute() {
  return (
    <Suspense fallback={<p aria-busy="true">Loading viewer</p>}>
      <PdfViewerPage />
    </Suspense>
  );
}
