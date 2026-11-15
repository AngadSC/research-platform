import { useCallback, useState } from "react";

/** How one person likes a page laid out in one project. Kept in this browser, per project. */
export interface RegistryView {
  density: "comfortable" | "compact";
  /** Data columns hidden from the grid. They still count toward progress. */
  hidden: string[];
  /** Show the "Done" column and the totals row. */
  totals: boolean;
  /** Show the keyboard help line under the grid. */
  help: boolean;
  /** Show the filter row without having to open it. */
  filters: boolean;
}

export const DEFAULT_VIEW: RegistryView = {
  density: "comfortable",
  hidden: [],
  totals: true,
  help: false,
  filters: false,
};

const key = (scope: string, projectId: string) => `view:${scope}:${projectId}`;

function read<T extends object>(scope: string, projectId: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key(scope, projectId));
    return raw ? { ...fallback, ...(JSON.parse(raw) as Partial<T>) } : fallback;
  } catch {
    return fallback;
  }
}

/** Layout choices for a page, remembered per project. Works without storage, just not remembered. */
export function useViewPrefs<T extends object>(scope: string, projectId: string, fallback: T) {
  const [view, setView] = useState<T>(() => read(scope, projectId, fallback));
  const update = useCallback(
    (patch: Partial<T>) =>
      setView((v) => {
        const next = { ...v, ...patch };
        try {
          localStorage.setItem(key(scope, projectId), JSON.stringify(next));
        } catch {
          /* the choice just isn't remembered */
        }
        return next;
      }),
    [scope, projectId],
  );
  const reset = useCallback(() => {
    setView(fallback);
    try {
      localStorage.removeItem(key(scope, projectId));
    } catch {
      /* nothing to forget */
    }
  }, [scope, projectId, fallback]);
  return { view, update, reset };
}
