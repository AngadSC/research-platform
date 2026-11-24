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

export interface GridItem {
  id: string;
  name: string;
  /** A short line under the name, such as "Document" or "PDF · 2 MB". */
  meta?: ReactNode;
  icon: ReactNode;
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
            <span className="flex h-24 items-center justify-center rounded-md bg-muted text-muted-foreground [&_svg]:size-9">
              {it.icon}
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
