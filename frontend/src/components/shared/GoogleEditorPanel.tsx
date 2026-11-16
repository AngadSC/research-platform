import { ExternalLink, GripHorizontal, PanelRight, PictureInPicture2, X } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties, type PointerEvent } from "react";
import {
  announcePanel,
  DockHandle,
  PANEL_OPENED,
  type PanelName,
} from "@/components/shared/DockHandle";
import { Button } from "@/components/ui/button";
import { closeGooglePanel, useGooglePanel } from "@/lib/googlePanel";
import { cn } from "@/lib/utils";

const MIN_W = 320;
const MIN_H = 240;
const EDGE = 80; // a moved or resized window always keeps this much on screen
const KEY = "google-panel";

interface Layout {
  mode: "dock" | "float";
  width: number; // docked
  x: number; // floating
  y: number;
  w: number;
  h: number;
}

/** Docked: up to the whole window but EDGE, so the page always shows a sliver to click back to. */
const dockMax = () => Math.max(MIN_W, window.innerWidth - EDGE);

function fit(l: Layout): Layout {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const w = Math.round(Math.min(vw, Math.max(MIN_W, l.w)));
  const h = Math.round(Math.min(vh, Math.max(MIN_H, l.h)));
  return {
    ...l,
    width: Math.round(Math.min(dockMax(), Math.max(MIN_W, l.width))),
    w,
    h,
    // Keep the title bar reachable: never above the top, never more than EDGE off any side.
    x: Math.round(Math.min(vw - EDGE, Math.max(EDGE - w, l.x))),
    y: Math.round(Math.min(vh - 40, Math.max(0, l.y))),
  };
}

function readLayout(): Layout {
  const fallback: Layout = {
    mode: "dock",
    width: 560,
    x: Math.max(0, window.innerWidth - 720),
    y: 80,
    w: 640,
    h: Math.max(MIN_H, window.innerHeight - 160),
  };
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? "null") as Partial<Layout> | null;
    if (!saved || typeof saved !== "object") return fit(fallback);
    const pick = (k: keyof Layout) =>
      typeof saved[k] === "number" && Number.isFinite(saved[k]) ? saved[k] : fallback[k];
    return fit({
      mode: saved.mode === "float" ? "float" : "dock",
      width: pick("width") as number,
      x: pick("x") as number,
      y: pick("y") as number,
      w: pick("w") as number,
      h: pick("h") as number,
    });
  } catch {
    return fit(fallback); // storage is blocked or holds something else
  }
}

/** Renders the open Google file, if any. Mounted once in the app shell, so it stays open while
 * the person moves between pages (D326). */
export function GoogleEditorHost() {
  const file = useGooglePanel();
  if (!file) return null;
  return <GoogleEditorPanel key={file.src} {...file} onClose={closeGooglePanel} />;
}

/** A Google Doc, Sheet or Slides file shown in Google's own page (D239, D326). From 768px up it
 * either docks on the right (the page makes room through --google-w, which AppShell pads by;
 * drag the divider to resize, up to nearly the whole window) or floats as a window you drag by
 * its title bar and resize from its corner. Dragging the title bar of the docked panel lifts
 * it into a window. On phones it covers the screen. Only the X closes it: not leaving the page,
 * not the assistant opening (a docked panel then floats instead). It runs on the person's own
 * Google sign-in and nothing goes through our server. A page cannot tell when Google refuses to
 * be framed, so "Open in Google" and the sign-in note are always on screen. */
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
  const [layout, setLayout] = useState(readLayout);
  const [moving, setMoving] = useState(false); // the frame ignores the pointer while dragging
  const drag = useRef<{ dx: number; dy: number } | null>(null);
  const docked = layout.mode === "dock";
  const update = (change: Partial<Layout>) => setLayout((l) => fit({ ...l, ...change }));

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(layout));
    } catch {
      // storage is blocked: the layout lasts until the page reloads
    }
    const root = document.documentElement.style;
    if (docked) root.setProperty("--google-w", `${layout.width}px`);
    else root.removeProperty("--google-w");
  }, [layout, docked]);
  useEffect(() => {
    const onResize = () => setLayout((l) => fit(l));
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      document.documentElement.style.removeProperty("--google-w");
    };
  }, []);
  // One docked panel at a time: when the assistant docks, this one floats rather than closing.
  useEffect(() => {
    if (docked) announcePanel("google");
    const onOther = (e: Event) => {
      if ((e as CustomEvent<PanelName>).detail === "assistant") update({ mode: "float" });
    };
    window.addEventListener(PANEL_OPENED, onOther);
    return () => window.removeEventListener(PANEL_OPENED, onOther);
  }, [docked]);

  function startMove(e: PointerEvent<HTMLDivElement>) {
    if (e.button !== 0 || (e.target as HTMLElement).closest("button, a")) return;
    if (window.innerWidth < 768) return; // full screen on phones
    const rect = e.currentTarget.parentElement!.getBoundingClientRect();
    drag.current = { dx: e.clientX - rect.left, dy: e.clientY - rect.top };
    if (docked) update({ mode: "float", x: rect.left, y: rect.top, w: rect.width });
    e.currentTarget.setPointerCapture(e.pointerId);
    setMoving(true);
  }
  function move(e: PointerEvent<HTMLDivElement>) {
    if (!drag.current || !e.currentTarget.hasPointerCapture(e.pointerId)) return;
    update({ x: e.clientX - drag.current.dx, y: e.clientY - drag.current.dy });
  }
  function endMove() {
    drag.current = null;
    setMoving(false);
  }

  const floatStyle: CSSProperties = docked
    ? ({ "--panel-w": `${layout.width}px` } as CSSProperties)
    : ({
        "--fx": `${layout.x}px`,
        "--fy": `${layout.y}px`,
        "--fw": `${layout.w}px`,
        "--fh": `${layout.h}px`,
      } as CSSProperties);

  return (
    <aside
      aria-label={`${title} in ${label}`}
      className={cn(
        "fixed z-40 flex w-full max-w-full flex-col bg-background print:hidden",
        docked
          ? "inset-y-0 right-0 border-l shadow-lg md:z-30 md:w-(--panel-w) md:shadow-none"
          : "inset-0 md:inset-auto md:top-(--fy) md:left-(--fx) md:h-(--fh) md:w-(--fw) md:rounded-lg md:border md:shadow-2xl",
      )}
      style={floatStyle}
    >
      {docked && (
        <div className="hidden md:contents">
          <DockHandle
            label="Resize panel"
            width={layout.width}
            min={MIN_W}
            max={dockMax()}
            onWidth={(w) => update({ width: w })}
          />
        </div>
      )}
      <div
        className="flex cursor-default items-center gap-2 border-b px-2 py-2 select-none md:cursor-grab md:active:cursor-grabbing"
        onPointerDown={startMove}
        onPointerMove={move}
        onPointerUp={endMove}
        onPointerCancel={endMove}
      >
        <Button variant="ghost" size="sm" aria-label="Close panel" onClick={onClose}>
          <X aria-hidden />
        </Button>
        <GripHorizontal
          className="hidden size-4 shrink-0 text-muted-foreground md:block"
          aria-hidden
        />
        <h2 className="min-w-0 flex-1 truncate text-sm font-semibold">{title}</h2>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="hidden md:inline-flex"
            aria-label={docked ? "Float as a window" : "Dock to the right"}
            title={docked ? "Float as a window" : "Dock to the right"}
            onClick={() => update({ mode: docked ? "float" : "dock" })}
          >
            {docked ? <PictureInPicture2 aria-hidden /> : <PanelRight aria-hidden />}
          </Button>
          <Button variant="outline" size="sm" asChild>
            <a href={openUrl} target="_blank" rel="noopener noreferrer">
              <ExternalLink aria-hidden /> Open in Google
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
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
        className={cn("min-h-0 w-full flex-1", moving && "pointer-events-none")}
      />
      {!docked && (
        <ResizeGrip
          onStart={() => setMoving(true)}
          onEnd={() => setMoving(false)}
          onSize={(w, h) => update({ w, h })}
          w={layout.w}
          h={layout.h}
        />
      )}
    </aside>
  );
}

/** The bottom-right corner of a floating window: drag it, or focus it and use the arrow keys. */
function ResizeGrip({
  w,
  h,
  onSize,
  onStart,
  onEnd,
}: {
  w: number;
  h: number;
  onSize: (w: number, h: number) => void;
  onStart: () => void;
  onEnd: () => void;
}) {
  const from = useRef<{ x: number; y: number; w: number; h: number } | null>(null);
  return (
    <div
      role="separator"
      aria-label="Resize window"
      aria-valuetext={`${w} by ${h} pixels`}
      tabIndex={0}
      className="absolute right-0 bottom-0 hidden size-4 cursor-nwse-resize touch-none rounded-br-lg bg-[linear-gradient(135deg,transparent_50%,var(--color-border)_50%)] focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none md:block"
      onPointerDown={(e) => {
        from.current = { x: e.clientX, y: e.clientY, w, h };
        e.currentTarget.setPointerCapture(e.pointerId);
        onStart();
      }}
      onPointerMove={(e) => {
        const f = from.current;
        if (f && e.currentTarget.hasPointerCapture(e.pointerId))
          onSize(f.w + e.clientX - f.x, f.h + e.clientY - f.y);
      }}
      onPointerUp={() => {
        from.current = null;
        onEnd();
      }}
      onPointerCancel={() => {
        from.current = null;
        onEnd();
      }}
      onKeyDown={(e) => {
        const dw = e.key === "ArrowRight" ? 24 : e.key === "ArrowLeft" ? -24 : 0;
        const dh = e.key === "ArrowDown" ? 24 : e.key === "ArrowUp" ? -24 : 0;
        if (!dw && !dh) return;
        e.preventDefault();
        onSize(w + dw, h + dh);
      }}
    />
  );
}
