import { ExternalLink, X } from "lucide-react";
import { useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from "react";
import { Button } from "@/components/ui/button";

const MIN = 320;
const MAX = 1000;

/** A Google Doc, Sheet or Slides file shown in Google's own page, docked on the right of the
 * page and resizable. It runs on the person's own Google sign-in and nothing goes through our
 * server (D239). A page cannot tell when Google refuses to be framed, so "Open in Google" and the
 * sign-in note are always on screen. */
export function GoogleEditorPanel({
  title,
  label,
  src,
  openUrl,
  onClose,
}: {
  title: string;
  label: string;
  src: string;
  openUrl: string;
  onClose: () => void;
}) {
  const [width, setWidth] = useState(560);
  const drag = useRef<{ x: number; w: number } | null>(null);
  const clamp = (w: number) => Math.min(MAX, Math.max(MIN, w));
  const move = (e: PointerEvent) => {
    if (drag.current) setWidth(clamp(drag.current.w + drag.current.x - e.clientX));
  };
  const key = (e: KeyboardEvent) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    setWidth((w) => clamp(w + (e.key === "ArrowLeft" ? 40 : -40)));
    e.preventDefault();
  };
  return (
    <aside
      aria-label={`${title} in ${label}`}
      className="relative flex h-[75dvh] w-full flex-col rounded-lg border bg-background lg:sticky lg:top-4 lg:h-[calc(100dvh-2rem)] lg:w-(--panel-w) lg:shrink-0"
      style={{ "--panel-w": `${width}px` } as CSSProperties}
    >
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize panel"
        aria-valuenow={width}
        aria-valuemin={MIN}
        aria-valuemax={MAX}
        tabIndex={0}
        onKeyDown={key}
        onPointerDown={(e) => {
          drag.current = { x: e.clientX, w: width };
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={move}
        onPointerUp={() => (drag.current = null)}
        className="absolute inset-y-0 -left-1.5 z-10 hidden w-3 cursor-col-resize touch-none rounded hover:bg-primary/20 focus-visible:bg-primary/30 focus-visible:outline-none lg:block"
      />
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
        <h2 className="truncate text-sm font-semibold">{title}</h2>
        <div className="flex shrink-0 items-center gap-1">
          <Button variant="outline" size="sm" asChild>
            <a href={openUrl} target="_blank" rel="noopener noreferrer">
              <ExternalLink aria-hidden /> Open in Google
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
          </Button>
          <Button variant="ghost" size="sm" aria-label="Close panel" onClick={onClose}>
            <X aria-hidden />
          </Button>
        </div>
      </div>
      <p className="border-b px-3 py-1.5 text-xs text-muted-foreground">
        If Google asks you to sign in, sign in to Google in this browser, or open it in a new tab.
      </p>
      <iframe
        title={title}
        src={src}
        // The same sandbox as embedded documents (DocumentPage), plus downloads for File > Download.
        sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox allow-downloads"
        referrerPolicy="no-referrer"
        className="min-h-0 w-full flex-1 rounded-b-lg"
      />
    </aside>
  );
}
