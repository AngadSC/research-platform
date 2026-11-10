import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router";
import { cn } from "@/lib/utils";

const tabClass = (active: boolean) =>
  cn(
    "-mb-px flex items-center gap-1.5 rounded-t-md border-b-[3px] px-3.5 py-2.5 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
    active
      ? "border-primary bg-primary/10 font-semibold text-primary"
      : "border-transparent font-medium text-muted-foreground hover:bg-muted hover:text-foreground",
  );

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
        <NavLink key={to} to={to} className={({ isActive }) => tabClass(isActive)}>
          {text}
          {badge}
        </NavLink>
      ))}
    </nav>
  );
}

/** Tabs kept in the address (#ai), so a link can open one. An unknown address shows the first. */
export function HashTabs({
  label,
  tabs,
}: {
  label: string;
  tabs: readonly { id: string; label: string; content: ReactNode }[];
}) {
  const { hash } = useLocation();
  const active = tabs.find((t) => `#${t.id}` === hash) ?? tabs[0];
  return (
    <>
      <nav aria-label={label} className="mb-6 flex flex-wrap gap-x-1 border-b">
        {tabs.map((t) => (
          <Link
            key={t.id}
            to={`#${t.id}`}
            aria-current={t === active ? "page" : undefined}
            className={tabClass(t === active)}
          >
            {t.label}
          </Link>
        ))}
      </nav>
      {active?.content}
    </>
  );
}
