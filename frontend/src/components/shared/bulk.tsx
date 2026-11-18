import { useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { formErrors } from "@/lib/forms";

export interface Selection {
  /** Selected keys that are still on screen. */
  keys: string[];
  has: (key: string) => boolean;
  /** Shift-click selects everything between the last click and this one. */
  toggle: (key: string, shift?: boolean) => void;
  /** The header checkbox: select every visible row, or clear when all are selected. */
  all: boolean | "some";
  toggleAll: () => void;
  clear: () => void;
}

/** Row selection for a list. `visible` is the keys on screen, in order. */
export function useSelection(visible: string[]): Selection {
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const last = useRef<string | null>(null);
  const keys = visible.filter((k) => picked.has(k));
  const toggle = (key: string, shift = false) => {
    const on = !picked.has(key);
    const from = last.current === null ? -1 : visible.indexOf(last.current);
    const at = visible.indexOf(key);
    const span =
      shift && from >= 0 ? visible.slice(Math.min(from, at), Math.max(from, at) + 1) : [key];
    const next = new Set(picked);
    for (const k of span) {
      if (on) next.add(k);
      else next.delete(k);
    }
    last.current = key;
    setPicked(next);
  };
  return {
    keys,
    has: (k) => picked.has(k),
    toggle,
    all: keys.length === 0 ? false : keys.length === visible.length ? true : "some",
    toggleAll: () => setPicked(keys.length === visible.length ? new Set() : new Set(visible)),
    clear: () => setPicked(new Set()),
  };
}

export function SelectBox({
  checked,
  label,
  onToggle,
}: {
  checked: boolean | "some";
  label: string;
  onToggle: (shift: boolean) => void;
}) {
  return (
    <input
      type="checkbox"
      className="size-4"
      aria-label={label}
      checked={checked === true}
      ref={(el) => {
        if (el) el.indeterminate = checked === "some";
      }}
      onChange={() => {}}
      onClick={(e) => {
        e.stopPropagation();
        onToggle(e.shiftKey);
      }}
    />
  );
}

/** "N selected" and Clear, with the actions that apply. Shows nothing until a row is picked. */
export function BulkBar({ selection, children }: { selection: Selection; children: ReactNode }) {
  if (selection.keys.length === 0) return null;
  return (
    <div
      role="toolbar"
      aria-label="Actions for the selected rows"
      className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/40 px-3 py-2"
    >
      <span className="text-sm font-medium" aria-live="polite">
        {selection.keys.length} selected
      </span>
      <Button variant="ghost" size="sm" onClick={selection.clear}>
        Clear
      </Button>
      <span className="mx-1 hidden h-5 w-px bg-border sm:block" aria-hidden />
      {children}
    </div>
  );
}

/** Run one request per item, one after another, and say plainly what did not go through. */
export async function runEach<T>(
  items: T[],
  run: (item: T) => Promise<unknown>,
  nameOf: (item: T) => string,
): Promise<{ done: number; failed: { name: string; why: string }[] }> {
  const failed: { name: string; why: string }[] = [];
  for (const item of items) {
    try {
      await run(item);
    } catch (e) {
      failed.push({
        name: nameOf(item),
        why: formErrors(e, []).form ?? "It could not be changed.",
      });
    }
  }
  return { done: items.length - failed.length, failed };
}

type Outcome = Awaited<ReturnType<typeof runEach>>;

/** One toast: all done, or what went through and exactly which ones did not and why. */
export function reportBulk(past: string, noun: string, total: number, r: Outcome): void {
  if (r.failed.length === 0) {
    toast.success(`${past} ${total} ${noun}${total === 1 ? "" : "s"}`);
    return;
  }
  const why = r.failed.map((f) => `${f.name}: ${f.why}`).join(" ");
  toast.error(`${past} ${r.done} of ${total}. Not ${past.toLowerCase()}: ${why}`, {
    duration: 15000,
  });
}
