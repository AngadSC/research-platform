import { Download } from "lucide-react";
import { lazy, Suspense, useEffect, useState } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { downloadUrl } from "@/hooks/projects";
import type { Attachment } from "@/lib/api-types";
import { isImage } from "@/lib/googleFiles";

// pdf.js stays out of the main bundle until a PDF is previewed.
const PdfView = lazy(() => import("@/pages/project/PdfView"));

/** An uploaded image or PDF in a dialog. The bytes come only through the authenticated download
 * endpoint (never a public address) and are shown from this page's own memory. */
export function FilePreview({
  labId,
  file,
  fullPage,
  onClose,
}: {
  labId: string;
  file: Attachment;
  /** Where the full-page PDF viewer lives. */
  fullPage: string;
  onClose: () => void;
}) {
  const url = downloadUrl(labId, file.id);
  const image = isImage(file);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] max-w-4xl grid-rows-[auto_minmax(0,1fr)] gap-3 overflow-y-auto p-4">
        <div className="flex items-center justify-between gap-2 pr-8">
          <DialogTitle className="truncate text-base font-semibold">
            {file.original_filename}
          </DialogTitle>
          <div className="flex shrink-0 gap-1">
            {!image && (
              <Button variant="outline" size="sm" asChild>
                <Link to={fullPage}>Full page</Link>
              </Button>
            )}
            <Button variant="outline" size="sm" asChild>
              <a href={url} download>
                <Download aria-hidden /> Download
              </a>
            </Button>
          </div>
        </div>
        <DialogDescription className="sr-only">
          Preview of {file.original_filename}
        </DialogDescription>
        {image ? (
          <ImageView url={url} name={file.original_filename} />
        ) : (
          <Suspense fallback={<Skeleton className="h-[60vh] w-full" />}>
            <PdfView url={url} />
          </Suspense>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ImageView({ url, name }: { url: string; name: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let blob: string | undefined;
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch(url, { credentials: "same-origin" });
        if (!res.ok) throw new Error(String(res.status));
        blob = URL.createObjectURL(await res.blob());
        if (cancelled) URL.revokeObjectURL(blob);
        else setSrc(blob);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
      if (blob) URL.revokeObjectURL(blob);
    };
  }, [url]);
  if (failed)
    return (
      <p role="alert" className="rounded-lg border p-6 text-sm">
        We couldn't open this image. You can still download it.
      </p>
    );
  if (!src)
    return <Skeleton aria-busy="true" aria-label="Loading image" className="h-[60vh] w-full" />;
  return <img src={src} alt={name} className="mx-auto max-h-[70dvh] max-w-full object-contain" />;
}
