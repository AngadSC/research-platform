import { useEffect, useRef } from "react";
import { toast } from "sonner";

/** How often open file, document and analysis lists re-check the server (tab visible only). */
export const LIVE_POLL_MS = 10_000;

/** Ids this tab created itself, so they never toast as "new". */
const mine = new Set<string>();
export const markMine = (id: string | undefined) => {
  if (id) mine.add(id);
};

type Item = { id: string; source?: string };

/** Toasts for items that show up in a list after the first load, unless this tab made them. */
export function useNewItemToasts<T extends Item>(
  scope: string,
  rows: T[] | undefined,
  label: string,
  name: (r: T) => string,
) {
  const seen = useRef<{ scope: string; ids: Set<string> } | null>(null);
  useEffect(() => {
    if (!rows) return;
    if (seen.current?.scope !== scope) {
      seen.current = { scope, ids: new Set(rows.map((r) => r.id)) };
      return;
    }
    for (const r of rows) {
      if (seen.current.ids.has(r.id)) continue;
      seen.current.ids.add(r.id);
      if (mine.has(r.id)) continue;
      toast(`${r.source === "link" ? "New from Claude" : `New ${label}`}: ${name(r)}`);
    }
  }, [scope, rows, label, name]);
}
