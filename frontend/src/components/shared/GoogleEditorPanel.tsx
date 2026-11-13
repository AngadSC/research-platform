import { ExternalLink, X } from "lucide-react";
import { useEffect, useState, type CSSProperties } from "react";
import {
  announcePanel,
  DockHandle,
  PANEL_OPENED,
  type PanelName,
} from "@/components/shared/DockHandle";
import { Button } from "@/components/ui/button";

const MIN = 320;
const MAX = 1000;
const KEY = "google-dock-width";
const clamp = (w: number) => Math.round(Math.min(MAX, Math.max(MIN, w)));
const readWidth = () => {
  try {
    return clamp(Number(localStorage.getItem(KEY)) || 560);
  } catch {
    return 560; // storage is blocked
  }
};

/** A Google Doc, Sheet or Slides file shown in Google's own page. From 768px up it docks on the
 * right like the assistant (the page makes room through --google-w, which AppShell pads by) and
 * is resized by dragging the divider; on phones it covers the screen. Only one docked panel is
 * open at a time: opening this closes the assistant and the other way round. It runs on the
 * person's own Google sign-in and nothing goes through our server (D239). A page cannot tell
 * when Google refuses to be framed, so "Open in Google" and the sign-in note are always on
 * screen. */
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
  const [width, setWidth] = useState(readWidth);
  useEffect(() => {
    try {
      localStorage.setItem(KEY, String(width));
    } catch {
      // storage is blocked: the width lasts until the page reloads
    }
    document.documentElement.style.setProperty("--google-w", `${width}px`);
  }, [width]);
  useEffect(() => {
    announcePanel("google");
    const onOther = (e: Event) => {
      if ((e as CustomEvent<PanelName>).detail === "assistant") onClose();
    };
    window.addEventListener(PANEL_OPENED, onOther);
    return () => {
      window.removeEventListener(PANEL_OPENED, onOther);
      document.documentElement.style.removeProperty("--google-w");
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- announce once per open
  }, []);
  return (
    <aside
      aria-label={`${title} in ${label}`}
      className="fixed inset-y-0 right-0 z-40 flex w-full max-w-full flex-col border-l bg-background shadow-lg md:z-30 md:w-(--panel-w) md:shadow-none print:hidden"
      style={{ "--panel-w": `${width}px` } as CSSProperties}
    >
      <div className="hidden md:contents">
        <DockHandle
          label="Resize panel"
          width={width}
          min={MIN}
          max={MAX}
          onWidth={(w) => setWidth(clamp(w))}
        />
      </div>
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
        className="min-h-0 w-full flex-1 "
      />
    </aside>
  );
}
