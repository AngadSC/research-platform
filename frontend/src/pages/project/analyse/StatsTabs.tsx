import { Plus, X } from "lucide-react";
import type { KeyboardEvent } from "react";
import { cn } from "@/lib/utils";

/** Where a report stands: nothing yet, kept in the project as work in progress, or finished. */
export type ReportStatus = "new" | "progress" | "unsaved" | "saved";

export interface TabInfo {
  id: string;
  title: string;
  status: ReportStatus;
}

const STATUS: Record<ReportStatus, { label: string; dot: string }> = {
  new: { label: "Not started", dot: "bg-muted-foreground/40" },
  progress: { label: "In progress, saved to the project", dot: "bg-warning" },
  unsaved: { label: "Has results that are not saved", dot: "bg-danger" },
  saved: { label: "Finished, saved to the project", dot: "bg-success" },
};

/**
 * One tab per statistics report, like browser tabs: pick one to work on it, "+" for a new report,
 * the cross to close it. Every report keeps its own data, test, options and results.
 */
export function StatsTabs({
  tabs,
  activeId,
  onSelect,
  onNew,
  onClose,
}: {
  tabs: TabInfo[];
  activeId: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  onClose: (id: string) => void;
}) {
  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    const i = tabs.findIndex((t) => t.id === activeId);
    const to =
      e.key === "ArrowRight"
        ? (i + 1) % tabs.length
        : e.key === "ArrowLeft"
          ? (i - 1 + tabs.length) % tabs.length
          : e.key === "Home"
            ? 0
            : e.key === "End"
              ? tabs.length - 1
              : -1;
    if (to < 0) return;
    e.preventDefault();
    const next = tabs[to]!;
    onSelect(next.id);
    requestAnimationFrame(() => document.getElementById(`report-tab-${next.id}`)?.focus());
  }

  return (
    <div className="flex items-end gap-1 border-b">
      <div
        role="tablist"
        aria-label="Reports"
        onKeyDown={onKey}
        className="flex min-w-0 items-end gap-1 overflow-x-auto"
      >
        {tabs.map((t) => {
          const active = t.id === activeId;
          const s = STATUS[t.status];
          return (
            <div
              key={t.id}
              role="presentation"
              className={cn(
                "group -mb-px flex max-w-56 min-w-28 shrink-0 items-center rounded-t-lg border border-b-0 text-sm",
                active ? "bg-background font-medium" : "border-transparent hover:bg-accent",
              )}
            >
              <button
                type="button"
                role="tab"
                id={`report-tab-${t.id}`}
                aria-selected={active}
                aria-controls={`report-panel-${t.id}`}
                tabIndex={active ? 0 : -1}
                title={`${t.title}: ${s.label}`}
                onClick={() => onSelect(t.id)}
                className="flex min-w-0 flex-1 items-center gap-2 rounded-tl-lg py-1.5 pr-1 pl-3 text-left focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                <span aria-hidden className={cn("size-2 shrink-0 rounded-full", s.dot)} />
                <span className="truncate">{t.title}</span>
                <span className="sr-only">{`, ${s.label}`}</span>
              </button>
              <button
                type="button"
                aria-label={`Close ${t.title}`}
                onClick={() => onClose(t.id)}
                className="mr-1 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </div>
          );
        })}
      </div>
      <button
        type="button"
        aria-label="New report"
        title="New report"
        onClick={onNew}
        className="mb-1 shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        <Plus className="size-4" aria-hidden />
      </button>
    </div>
  );
}
