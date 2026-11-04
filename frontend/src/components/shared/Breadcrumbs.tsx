import { ChevronRight } from "lucide-react";
import { Link } from "react-router";

export interface Crumb {
  label: string;
  to?: string;
}

/** The last crumb is the current page and is not a link. */
export function Breadcrumbs({ items }: { items: Crumb[] }) {
  if (items.length === 0) return null;
  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex items-center gap-1.5 text-sm text-muted-foreground">
        {items.map((item, i) => {
          const last = i === items.length - 1;
          return (
            <li key={`${i}-${item.label}`} className="flex items-center gap-1.5">
              {last || !item.to ? (
                <span
                  aria-current={last ? "page" : undefined}
                  className={last ? "text-foreground" : ""}
                >
                  {item.label}
                </span>
              ) : (
                <Link
                  to={item.to}
                  className="rounded-sm hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
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
