import { ArrowDown, ArrowUp, Copy, Play, Plus, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface Slide {
  type: "slide";
  props: { layout: "title" | "content" };
  title: { text: string };
  body: { text: string };
}

export const newSlide = (layout: Slide["props"]["layout"] = "content"): Slide => ({
  type: "slide",
  props: { layout },
  title: { text: "" },
  body: { text: "" },
});

/** The slides stored in a presentation's content, or a title slide to start from. */
export function slidesOf(content: unknown[]): Slide[] {
  const slides = content.filter((b) => (b as { type?: string })?.type === "slide") as Slide[];
  return slides.length ? slides : [newSlide("title")];
}

function Canvas({
  slide,
  editable,
  onChange,
  big = false,
}: {
  slide: Slide;
  editable: boolean;
  onChange?: (s: Slide) => void;
  big?: boolean;
}) {
  const title = slide.props.layout === "title";
  const field = (key: "title" | "body", cls: string, placeholder: string, rows: number) =>
    editable ? (
      <textarea
        aria-label={key === "title" ? "Slide title" : "Slide text"}
        placeholder={placeholder}
        rows={rows}
        value={slide[key].text}
        onChange={(e) => onChange?.({ ...slide, [key]: { text: e.target.value } })}
        className={cn(
          "w-full resize-none bg-transparent outline-none placeholder:text-muted-foreground/60",
          cls,
        )}
      />
    ) : (
      <p className={cn("whitespace-pre-wrap", cls)}>{slide[key].text}</p>
    );
  return (
    <div
      className={cn(
        "flex aspect-video w-full flex-col justify-center gap-4 rounded-lg border bg-card p-[5%] shadow-sm",
        title && "items-center text-center",
      )}
    >
      {field(
        "title",
        cn("font-semibold", title ? "text-3xl" : "text-2xl", big && "text-5xl"),
        "Click to add a title",
        2,
      )}
      {field(
        "body",
        cn("text-muted-foreground", big ? "text-2xl" : "text-base"),
        title ? "Subtitle" : "Click to add text",
        title ? 2 : 8,
      )}
    </div>
  );
}

/** A small presentation editor: a strip of slides, the slide being edited, and full-screen
 * presenting with the arrow keys. */
export function Slides({
  slides,
  onChange,
  editable,
  label,
}: {
  slides: Slide[];
  onChange?: (next: Slide[]) => void;
  editable: boolean;
  label: string;
}) {
  const [at, setAt] = useState(0);
  const [presenting, setPresenting] = useState(false);
  const i = Math.min(at, slides.length - 1);
  const set = (next: Slide[], to = i) => {
    onChange?.(next);
    setAt(Math.max(0, Math.min(to, next.length - 1)));
  };
  const swap = (a: number, b: number) => {
    if (b < 0 || b >= slides.length) return;
    const next = [...slides];
    [next[a], next[b]] = [next[b]!, next[a]!];
    set(next, b);
  };

  useEffect(() => {
    if (!presenting) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPresenting(false);
      else if (["ArrowRight", "ArrowDown", "PageDown", " "].includes(e.key))
        setAt((n) => Math.min(slides.length - 1, n + 1));
      else if (["ArrowLeft", "ArrowUp", "PageUp"].includes(e.key)) setAt((n) => Math.max(0, n - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [presenting, slides.length]);

  return (
    <div
      role="group"
      aria-label={label}
      className="grid min-w-0 overflow-hidden rounded-lg border bg-background"
    >
      <div
        role="toolbar"
        aria-label="Presentation tools"
        className="flex flex-wrap items-center gap-0.5 border-b bg-muted/40 p-1"
      >
        {editable && (
          <>
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                set([...slides.slice(0, i + 1), newSlide(), ...slides.slice(i + 1)], i + 1)
              }
            >
              <Plus aria-hidden /> New slide
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="size-8"
              aria-label="Duplicate slide"
              onClick={() =>
                set(
                  [...slides.slice(0, i + 1), structuredClone(slides[i]!), ...slides.slice(i + 1)],
                  i + 1,
                )
              }
            >
              <Copy aria-hidden />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="size-8"
              aria-label="Move slide up"
              disabled={i === 0}
              onClick={() => swap(i, i - 1)}
            >
              <ArrowUp aria-hidden />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="size-8"
              aria-label="Move slide down"
              disabled={i === slides.length - 1}
              onClick={() => swap(i, i + 1)}
            >
              <ArrowDown aria-hidden />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="size-8"
              aria-label="Delete slide"
              disabled={slides.length === 1}
              onClick={() =>
                set(
                  slides.filter((_, j) => j !== i),
                  i - 1,
                )
              }
            >
              <Trash2 aria-hidden />
            </Button>
            <select
              aria-label="Slide layout"
              value={slides[i]!.props.layout}
              onChange={(e) =>
                set(
                  slides.map((s, j) =>
                    j === i
                      ? { ...s, props: { layout: e.target.value as Slide["props"]["layout"] } }
                      : s,
                  ),
                )
              }
              className="ml-1 h-8 rounded-md border bg-background px-2 text-sm"
            >
              <option value="title">Title slide</option>
              <option value="content">Title and text</option>
            </select>
          </>
        )}
        <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setPresenting(true)}>
          <Play aria-hidden /> Present
        </Button>
      </div>
      <div className="grid min-h-96 grid-cols-[9rem_1fr] max-md:grid-cols-1">
        <ol
          aria-label="Slides"
          className="flex gap-2 overflow-auto border-r bg-muted/30 p-2 max-md:border-r-0 max-md:border-b md:grid md:content-start"
        >
          {slides.map((s, j) => (
            <li key={j}>
              <button
                type="button"
                aria-label={`Slide ${j + 1}${s.title.text ? `: ${s.title.text}` : ""}`}
                aria-current={j === i}
                onClick={() => setAt(j)}
                className={cn(
                  "flex w-28 gap-1 rounded-md border p-1 text-left text-[10px] md:w-full",
                  j === i ? "border-primary bg-background" : "bg-background/60 hover:bg-background",
                )}
              >
                <span className="text-muted-foreground">{j + 1}</span>
                <span className="line-clamp-3 font-medium">{s.title.text || "Untitled"}</span>
              </button>
            </li>
          ))}
        </ol>
        <div className="p-4">
          <Canvas
            slide={slides[i]!}
            editable={editable}
            onChange={(s) => set(slides.map((o, j) => (j === i ? s : o)))}
          />
        </div>
      </div>
      {presenting && (
        <div
          role="dialog"
          aria-label="Presenting"
          aria-modal
          className="fixed inset-0 z-[60] grid place-items-center bg-background p-8"
        >
          <Button
            variant="ghost"
            size="icon"
            className="absolute top-3 right-3"
            aria-label="Stop presenting"
            onClick={() => setPresenting(false)}
          >
            <X aria-hidden />
          </Button>
          <div className="w-full max-w-6xl">
            <Canvas slide={slides[i]!} editable={false} big />
          </div>
          <p className="absolute bottom-3 text-xs text-muted-foreground">
            {i + 1} of {slides.length} · arrow keys to move · Esc to stop
          </p>
        </div>
      )}
    </div>
  );
}
