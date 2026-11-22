import { CalendarDays, Home, ListChecks, Menu, MessagesSquare } from "lucide-react";
import { NavLink } from "react-router";
import { cn } from "@/lib/utils";

/** Below md: Home, My work, Calendar, Chat and a More button that opens the full menu. */
export function MobileTabBar({ labId, onMore }: { labId?: string; onMore: () => void }) {
  if (!labId) return null;
  const items = [
    ["dashboard", "Home", Home],
    ["my-work", "My work", ListChecks],
    ["calendar", "Calendar", CalendarDays],
    ["chat", "Chat", MessagesSquare],
  ] as const;
  const tab =
    "flex min-h-12 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl text-[11px] font-medium focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none [&_svg]:size-5";
  return (
    <nav
      aria-label="Quick navigation"
      className="glass glass--strong glass--float !bg-[color-mix(in_srgb,var(--card)_96%,transparent)] fixed inset-x-3 bottom-3 z-30 flex gap-1 rounded-2xl p-1.5 md:hidden print:hidden"
    >
      {items.map(([path, label, Icon]) => (
        <NavLink
          key={path}
          to={`/labs/${labId}/${path}`}
          className={({ isActive }) =>
            cn(tab, isActive ? "glass-pill-active text-primary" : "text-muted-foreground")
          }
        >
          <Icon aria-hidden />
          {label}
        </NavLink>
      ))}
      <button type="button" onClick={onMore} className={cn(tab, "text-muted-foreground")}>
        <Menu aria-hidden />
        More
      </button>
    </nav>
  );
}
