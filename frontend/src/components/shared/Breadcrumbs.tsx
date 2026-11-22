import { ChevronRight } from "lucide-react";
import { Link } from "react-router";
import { Skeleton } from "@/components/ui/skeleton";
import type { RecentKind } from "@/lib/pins";

export interface Crumb {
  label: string;
  to?: string;
  /** This crumb is a named item, which can appear in Recents. */
  kind?: RecentKind;
  /** The label is still a placeholder: the item's name has not loaded. */
  pending?: boolean;
}

/** The last crumb is the current page and is not a link. */
export function Breadcrumbs({
  items: all,
  label = "Breadcrumb",
}: {
  items: Crumb[];
  /** Give a second breadcrumb on one page its own landmark name. */
  label?: string;
}) {
  // "Home > Labs > Lab > Home": the page called the same as the root is the root, show it once.
  const items =
    all.length > 1 && !all[0].pending && all[all.length - 1].label === all[0].label
      ? all.slice(0, -1)
      : all;
  if (items.length === 0) return null;
  return (
    <nav aria-label={label}>
      <ol className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-sm text-muted-foreground">
        {items.map((item, i) => {
          const last = i === items.length - 1;
          // On phones only the last two crumbs fit.
          const show = i >= items.length - 2 ? "flex" : "hidden md:flex";
          if (item.pending)
            return (
              <li key={i} className={`${show} items-center gap-1.5`}>
                <Skeleton aria-label="Loading" className="h-4 w-20" />
                {!last && <ChevronRight className="size-3.5" aria-hidden />}
              </li>
            );
          return (
            <li key={`${i}-${item.label}`} className={`${show} min-w-0 items-center gap-1.5`}>
              {last || !item.to ? (
                <span
                  aria-current={last ? "page" : undefined}
                  title={item.label}
                  className={`block max-w-[12rem] truncate md:max-w-none ${last ? "text-foreground" : ""}`}
                >
                  {item.label}
                </span>
              ) : (
                <Link
                  to={item.to}
                  title={item.label}
                  className="block max-w-[12rem] truncate rounded-sm md:max-w-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  {item.label}
                </Link>
              )}
              {!last && <ChevronRight className="size-3.5" aria-hidden />}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
