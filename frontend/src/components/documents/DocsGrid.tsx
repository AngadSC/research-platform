import { LayoutGrid, List } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import type { DocsView } from "@/hooks/docsView";

/** One icon button that flips between list and grid. */
export function ViewToggle({
  view,
  onChange,
}: {
  view: DocsView;
  onChange: (v: DocsView) => void;
}) {
  const grid = view === "grid";
  return (
    <Button
      variant="outline"
      size="icon"
      aria-label={grid ? "Show as list" : "Show as grid"}
      title={grid ? "Show as list" : "Show as grid"}
      onClick={() => onChange(grid ? "list" : "grid")}
    >
      {grid ? <List aria-hidden /> : <LayoutGrid aria-hidden />}
    </Button>
  );
}

/** What the server sends to draw a document at thumbnail size (documents/text.py `preview_of`). */
export type DocPreview =
  | { kind: "doc"; text: string }
  | { kind: "sheet"; rows: string[][] }
  | { kind: "slides"; title: string; text: string };

/** A small picture of a document: a page of text, the corner of a spreadsheet, or the first slide. */
export function PreviewTile({ preview }: { preview?: unknown }) {
  const p = preview as DocPreview | undefined;
  if (!p || typeof p !== "object" || !("kind" in p)) return null;
  if (p.kind === "sheet") {
    return (
      <div aria-hidden className="size-full overflow-hidden bg-background p-1.5">
        <table className="w-full table-fixed border-collapse text-[7px] leading-tight">
          <tbody>
            {p.rows.map((row, r) => (
              <tr key={r}>
                {row.map((cell, c) => (
                  <td key={c} className="h-3 truncate border px-0.5 text-foreground">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  if (p.kind === "slides") {
    return (
      <div aria-hidden className="grid size-full place-items-center bg-background p-2">
        <div className="grid aspect-video w-full content-center justify-items-center gap-0.5 rounded border bg-card p-1 text-center">
          <span className="line-clamp-2 text-[9px] font-semibold text-foreground">{p.title}</span>
          <span className="line-clamp-2 text-[6px] text-muted-foreground">{p.text}</span>
        </div>
      </div>
    );
  }
  if (!p.text) return null;
  return (
    <div aria-hidden className="size-full overflow-hidden bg-background px-2.5 py-2 text-left">
      <p className="line-clamp-[9] text-[7px] leading-snug break-words text-foreground">{p.text}</p>
    </div>
  );
}

export interface GridItem {
  id: string;
  name: string;
  /** A short line under the name, such as "Document" or "PDF · 2 MB". */
  meta?: ReactNode;
  icon: ReactNode;
  /** A picture of the content, or the server's preview data; the icon shows when there is none. */
  preview?: ReactNode;
  onOpen: () => void;
  /** The item's own "..." menu. */
  menu?: ReactNode;
}

/** Cards about the size of Google Drive's grid: an icon tile on top, the name and kind below. */
export function DocsGrid({ items }: { items: GridItem[] }) {
  return (
    <ul className="grid grid-cols-[repeat(auto-fill,minmax(10.5rem,1fr))] gap-3">
      {items.map((it) => (
        <li key={it.id} className="group">
          <button
            type="button"
            onClick={it.onOpen}
            className="grid w-full gap-2 rounded-lg border bg-card p-2 text-left transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            <span className="flex h-32 items-center justify-center overflow-hidden rounded-md border bg-muted text-muted-foreground [&_svg]:size-9">
              {it.preview ?? it.icon}
            </span>
            <span className="grid min-w-0 gap-0.5 px-1 pb-1">
              <span className="truncate text-sm font-medium" title={it.name}>
                {it.name}
              </span>
              {it.meta && <span className="truncate text-xs text-muted-foreground">{it.meta}</span>}
            </span>
          </button>
          {it.menu && <div className="mt-1 flex justify-end">{it.menu}</div>}
        </li>
      ))}
    </ul>
  );
}
