import type { ReactNode } from "react";
import { NavLink } from "react-router";
import { cn } from "@/lib/utils";

/** Link tabs with a strong underline on the active one; NavLink supplies aria-current="page". */
export function TabNav({
  label,
  tabs,
  className,
}: {
  label: string;
  tabs: readonly (readonly [string, string, ReactNode?])[];
  className?: string;
}) {
  return (
    <nav aria-label={label} className={cn("flex flex-wrap gap-x-1 border-b", className)}>
      {tabs.map(([to, text, badge]) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            cn(
              "-mb-px flex items-center gap-1.5 rounded-t-md border-b-[3px] px-3.5 py-2.5 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
              isActive
                ? "border-primary bg-primary/10 font-semibold text-primary"
                : "border-transparent font-medium text-muted-foreground hover:bg-muted hover:text-foreground",
            )
          }
        >
          {text}
          {badge}
        </NavLink>
      ))}
    </nav>
  );
}
