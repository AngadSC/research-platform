import { ChevronsUpDown, LogOut } from "lucide-react";
import { NavLink, useNavigate } from "react-router";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import { ThemeToggle } from "@/components/shared/ThemeToggle";
import { useLogout } from "@/hooks/auth";
import { useCurrentLabId } from "@/hooks/crumbs";
import { useLabs } from "@/hooks/workspace";
import type { Lab } from "@/lib/api-types";
import { navItems } from "@/lib/nav";
import { APP_NAME } from "@/lib/constants";
import { cn } from "@/lib/utils";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none [&_svg]:size-4",
    isActive
      ? "bg-accent font-medium text-accent-foreground"
      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
  );

function LabSwitcher({ labs, current }: { labs: Lab[]; current: Lab | undefined }) {
  const navigate = useNavigate();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label="Switch lab"
        className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-2 text-left text-sm font-semibold hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        <span className="truncate">{current?.name ?? "Select a lab"}</span>
        <ChevronsUpDown className="size-4 shrink-0 opacity-60" aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <DropdownMenuLabel>Switch lab</DropdownMenuLabel>
        {labs.map((lab) => (
          <DropdownMenuItem key={lab.id} onSelect={() => void navigate(`/labs/${lab.id}`)}>
            {lab.name}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void navigate("/labs/new")}>
          Create a lab
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function Sidebar() {
  const { data: labs = [] } = useLabs();
  const labId = useCurrentLabId();
  const logout = useLogout();
  const current = labs.find((l) => l.id === labId);
  return (
    <aside className="flex w-64 shrink-0 flex-col gap-4 border-r bg-sidebar p-3">
      <div>
        <p className="px-2 pb-1 text-xs text-muted-foreground">{APP_NAME}</p>
        <LabSwitcher labs={labs} current={current} />
      </div>
      <Separator />
      <nav aria-label="Main" className="grid gap-0.5">
        {navItems(labId).map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={linkClass}>
            <Icon aria-hidden />
            {label}
          </NavLink>
        ))}
        <button
          type="button"
          onClick={() => logout.mutate()}
          className={cn(linkClass({ isActive: false }), "w-full text-left")}
        >
          <LogOut aria-hidden />
          Sign out
        </button>
      </nav>
      <div className="mt-auto flex items-center justify-between">
        <span className="px-2 text-xs text-muted-foreground">Ctrl K to search</span>
        <ThemeToggle />
      </div>
    </aside>
  );
}
