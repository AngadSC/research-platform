import { Download, Minus, Plus, StretchHorizontal } from "lucide-react";
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Link, useParams } from "react-router";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { downloadUrl, useAttachment } from "@/hooks/projects";

GlobalWorkerOptions.workerSrc = workerUrl;

type Zoom = number | "fit";

export default function PdfViewerPage() {
  const { labId = "", projectId = "", attachmentId = "" } = useParams();
  const url = downloadUrl(labId, attachmentId);
  const { data: att } = useAttachment(labId, attachmentId);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [failed, setFailed] = useState(false);
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState<Zoom>("fit");
  const canvas = useRef<HTMLCanvasElement>(null);
  const wrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let task: ReturnType<typeof getDocument> | undefined;
    let cancelled = false;
    void (async () => {
      try {
        // Authenticated same-origin download endpoint only.
        const res = await fetch(url, { credentials: "same-origin" });
        if (!res.ok) throw new Error(String(res.status));
        task = getDocument({ data: new Uint8Array(await res.arrayBuffer()) });
        const doc = await task.promise;
        if (!cancelled) setPdf(doc);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
      void task?.destroy();
    };
  }, [url]);

  useEffect(() => {
    if (!pdf) return;
    let cancelled = false;
    void (async () => {
      const p = await pdf.getPage(page);
      const base = p.getViewport({ scale: 1 });
      const scale = zoom === "fit" ? ((wrap.current?.clientWidth ?? 800) - 2) / base.width : zoom;
      const vp = p.getViewport({ scale });
      const c = canvas.current;
      if (cancelled || !c) return;
      c.width = vp.width;
      c.height = vp.height;
      const ctx = c.getContext("2d");
      if (ctx) await p.render({ canvasContext: ctx, viewport: vp, canvas: c }).promise;
    })().catch(() => {
      if (!cancelled) setFailed(true);
    });
    return () => {
      cancelled = true;
    };
  }, [pdf, page, zoom]);

  const pages = pdf?.numPages ?? 1;
  const go = (n: number) => setPage(Math.min(Math.max(1, n), pages));
  const step = (d: number) =>
    setZoom((z) => Math.min(4, Math.max(0.25, (z === "fit" ? 1 : z) + d)));

  function onKey(e: KeyboardEvent) {
    if (e.key === "ArrowRight" || e.key === "PageDown") go(page + 1);
    else if (e.key === "ArrowLeft" || e.key === "PageUp") go(page - 1);
    else if (e.key === "+" || e.key === "=") step(0.25);
    else if (e.key === "-") step(-0.25);
    else if (e.key === "0") setZoom("fit");
    else return;
    e.preventDefault();
  }

  return (
    <div className="grid gap-4" onKeyDown={onKey}>
      <PageHeader
        title={att?.original_filename ?? "File"}
        actions={
          <>
            <Button variant="outline" asChild>
              <Link to={`/labs/${labId}/projects/${projectId}/files`}>Back to files</Link>
            </Button>
            <Button variant="outline" asChild>
              <a href={url} download>
                <Download aria-hidden /> Download
              </a>
            </Button>
          </>
        }
      />
      {failed ? (
        <div role="alert" className="rounded-lg border p-6 text-sm">
          <p className="font-medium">We couldn't open this file.</p>
          <p className="text-muted-foreground">
            It may have been removed, or it isn't a readable PDF. You can still download it.
          </p>
        </div>
      ) : !pdf ? (
        <div aria-busy="true" aria-label="Loading file">
          <Skeleton className="h-[70vh] w-full" />
        </div>
      ) : (
        <>
          <div
            role="toolbar"
            aria-label="Viewer controls"
            className="flex flex-wrap items-center gap-2"
          >
            <Button variant="outline" size="sm" onClick={() => go(page - 1)} disabled={page <= 1}>
              Previous
            </Button>
            <span className="text-sm" aria-live="polite">
              Page {page} of {pages}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => go(page + 1)}
              disabled={page >= pages}
            >
              Next
            </Button>
            <Button variant="ghost" size="sm" aria-label="Zoom out" onClick={() => step(-0.25)}>
              <Minus aria-hidden />
            </Button>
            <Button variant="ghost" size="sm" aria-label="Zoom in" onClick={() => step(0.25)}>
              <Plus aria-hidden />
            </Button>
            <Button variant="ghost" size="sm" aria-label="Fit width" onClick={() => setZoom("fit")}>
              <StretchHorizontal aria-hidden />
            </Button>
            <span className="text-xs text-muted-foreground">
              Arrow keys change page; + and - zoom; 0 fits width.
            </span>
          </div>
          <div
            ref={wrap}
            className="overflow-auto rounded-lg border bg-muted/30"
            tabIndex={0}
            aria-label="Document"
          >
            <canvas ref={canvas} />
          </div>
        </>
      )}
    </div>
  );
}
