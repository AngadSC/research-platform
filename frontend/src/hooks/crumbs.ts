import { useMatches } from "react-router";
import type { Crumb } from "@/components/shared/Breadcrumbs";
import { useLabs } from "@/hooks/workspace";

/** Routes declare `handle: { crumb: "Label" }`. The special label "@lab" becomes the current lab's name. */
export function useCrumbs(): Crumb[] {
  const matches = useMatches();
  const { data: labs } = useLabs();
  return matches.flatMap((m) => {
    let crumb = (m.handle as { crumb?: string } | undefined)?.crumb;
    if (crumb === "@lab") crumb = labs?.find((l) => l.id === m.params.labId)?.name ?? "Lab";
    return crumb ? [{ label: crumb, to: m.pathname }] : [];
  });
}

/** The lab id from the matched route, if the current page is inside a lab. */
export function useCurrentLabId(): string | undefined {
  return useMatches()
    .map((m) => m.params.labId)
    .find(Boolean);
}
