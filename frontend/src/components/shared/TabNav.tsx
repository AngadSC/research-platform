import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router";
import { cn } from "@/lib/utils";

const tabClass = (active: boolean) =>
  cn(
    "flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-sm transition-[background-color,box-shadow,color] duration-[var(--dur)] ease-[var(--ease-glass)] focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none max-md:py-2.5",
    active
      ? "glass-pill-active font-medium text-foreground"
      : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground",
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
    <nav
      aria-label={label}
      className={cn("glass-track flex w-fit max-w-full flex-wrap gap-x-1", className)}
    >
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
      <nav aria-label={label} className="glass-track mb-6 flex w-fit max-w-full flex-wrap gap-x-1">
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
