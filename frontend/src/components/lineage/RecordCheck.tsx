import { CheckCircle2, ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import { KIND_LABEL, type Gap } from "@/lib/lineage";
import { cn } from "@/lib/utils";

const KEY = "lineage-record-check-collapsed";
const read = () => {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
};

export function RecordCheck({ gaps, onSelect }: { gaps: Gap[]; onSelect: (id: string) => void }) {
  const [collapsed, setCollapsed] = useState(read);
  if (!gaps.length)
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <CheckCircle2 className="size-4 shrink-0" aria-hidden />
        Everything is linked: each analysis has its data and code recorded.
      </p>
    );
  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem(KEY, next ? "1" : "0");
    } catch {
      /* private mode: the card still works, it just forgets */
    }
  };
  const Chevron = collapsed ? ChevronRight : ChevronDown;
  return (
    <section aria-labelledby="record-check-h" className="rounded-lg border">
      <h3 id="record-check-h" className="text-sm font-semibold">
        <button
          type="button"
          aria-expanded={!collapsed}
          aria-controls="record-check-list"
          onClick={toggle}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left"
        >
          <Chevron className="size-4 shrink-0" aria-hidden />
          {gaps.length} {gaps.length === 1 ? "thing" : "things"} to check
        </button>
      </h3>
      {!collapsed && (
        <ul id="record-check-list" className="grid max-h-60 gap-px overflow-y-auto border-t">
          {gaps.map((g) => (
            <li key={`${g.nodeId}:${g.problem}`}>
              <button
                type="button"
                onClick={() => onSelect(g.nodeId)}
                className="grid w-full gap-0.5 px-3 py-2 text-left text-sm hover:bg-muted/50"
              >
                <span className="font-medium">
                  {g.title}{" "}
                  <span className="font-normal text-muted-foreground">{KIND_LABEL[g.kind]}</span>
                </span>
                <span className={cn(g.info ? "text-muted-foreground" : "text-warning-text")}>
                  {g.problem}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
