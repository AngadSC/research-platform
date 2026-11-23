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
      className="glass glass--solid fixed inset-x-0 bottom-0 z-30 flex gap-1 rounded-none border-0 border-t p-1.5 pb-[max(0.375rem,env(safe-area-inset-bottom))] shadow-none md:hidden print:hidden"
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
