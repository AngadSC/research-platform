import { useCallback, useState } from "react";

export type DocsView = "list" | "grid";

const DEFAULT_KEY = "docs-view-default";
const SEEN_KEY = "docs-view";

function read(key: string): DocsView | null {
  try {
    const v = localStorage.getItem(key);
    return v === "list" || v === "grid" ? v : null;
  } catch {
    return null; // storage is blocked
  }
}

function write(key: string, value: DocsView) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // the choice lasts until the page reloads
  }
}

/** The view new documents pages open in. Set in Settings; list until someone picks. */
export const getDefaultDocsView = (): DocsView => read(DEFAULT_KEY) ?? "list";
export const setDefaultDocsView = (v: DocsView) => write(DEFAULT_KEY, v);

/** List or grid for one documents page. Starts at the saved default; the toggle is remembered per page. */
export function useDocsView(scope: string) {
  const [view, setView] = useState<DocsView>(
    () => read(`${SEEN_KEY}:${scope}`) ?? getDefaultDocsView(),
  );
  const choose = useCallback(
    (v: DocsView) => {
      setView(v);
      write(`${SEEN_KEY}:${scope}`, v);
    },
    [scope],
  );
  return [view, choose] as const;
}
