import { useEffect, useState } from "react";
import { ChevronsUpDown, CircleHelp, LogOut, Settings, User, X } from "lucide-react";
import { NavLink, useNavigate } from "react-router";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { UserAvatar } from "@/components/shared/UserAvatar";
import { Skeleton } from "@/components/ui/skeleton";
import { useLogout } from "@/hooks/auth";
import { usePins } from "@/hooks/preferences";
import { useMe } from "@/hooks/workspace";
import { roleLabel } from "@/lib/api-types";
import { useTheme, type Theme } from "@/lib/theme";
import { cn } from "@/lib/utils";

/** A small-caps heading over a group of sidebar links. */
export const groupLabel =
  "px-3 pb-1 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase";

export const hoverTint = "hover:bg-primary/15 hover:text-foreground";

export const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "relative flex items-center gap-2 rounded-md px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none [&_svg]:size-4",
    isActive
      ? // The accent bar says where you are even where a grey fill is hard to see.
        "bg-primary/10 font-semibold text-primary before:absolute before:top-1.5 before:bottom-1.5 before:left-0 before:w-1 before:rounded-full before:bg-primary"
      : `text-muted-foreground ${hoverTint}`,
  );

export const iconButton = `shrink-0 rounded-md p-1 text-muted-foreground ${hoverTint} focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none [&_svg]:size-4`;

export function PinnedNav({ onNavigate }: { onNavigate: () => void }) {
  const { pins, toggle } = usePins();
  if (pins.length === 0) return null;
  return (
    <nav aria-label="Pinned" className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-0.5">
      <span className="px-2 pb-1 text-xs text-muted-foreground">Pinned</span>
      <ul className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-0.5">
        {pins.map((pin) => (
          <li key={pin.url} className="group flex items-center gap-0.5">
            <NavLink
              to={pin.url}
              end
              onClick={onNavigate}
              className={(s) => cn(linkClass(s), "min-w-0 flex-1")}
            >
              <span className="truncate">{pin.label}</span>
            </NavLink>
            {/* Always shown below md, where a touch screen has no hover. */}
            <button
              type="button"
              aria-label={`Unpin ${pin.label}`}
              onClick={() => toggle(pin)}
              className={cn(
                iconButton,
                "focus-visible:opacity-100 md:opacity-0 md:group-focus-within:opacity-100 md:group-hover:opacity-100",
              )}
            >
              <X aria-hidden />
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    let timer: number;
    const schedule = () => {
      timer = window.setTimeout(
        () => {
          setNow(new Date());
          schedule();
        },
        60_000 - (Date.now() % 60_000),
      ); // on the minute, however late the page opened
    };
    schedule();
    return () => window.clearTimeout(timer);
  }, []);
  return (
    <time dateTime={now.toISOString()} className="px-3 text-xs text-muted-foreground">
      {new Intl.DateTimeFormat(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      }).format(now)}
    </time>
  );
}

/** Time and the account menu, held at the bottom of the sidebar while the rest scrolls. */
export function SidebarFooter({
  onNavigate,
  role,
}: {
  onNavigate: () => void;
  role?: string | null;
}) {
  const me = useMe().data;
  const logout = useLogout();
  const navigate = useNavigate();
  const { theme, setTheme } = useTheme();
  const go = (to: string) => {
    onNavigate();
    void navigate(to);
  };
  return (
    <div className="sticky bottom-0 mt-auto grid gap-1 bg-sidebar pt-2">
      <Clock />
      <DropdownMenu>
        <DropdownMenuTrigger
          aria-label="Account menu"
          className={`flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm ${hoverTint} focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none`}
        >
          {me ? (
            <UserAvatar user={me} className="size-8" />
          ) : (
            <Skeleton className="size-8 rounded-full" />
          )}
          <span className="min-w-0 flex-1">
            <span className="block truncate font-medium">{me?.display_name || me?.email}</span>
            <span className="block truncate text-xs text-muted-foreground">
              {role ? roleLabel(role) : me?.email}
            </span>
          </span>
          <ChevronsUpDown className="size-4 shrink-0 opacity-60" aria-hidden />
        </DropdownMenuTrigger>
        <DropdownMenuContent
          side="top"
          align="start"
          className="w-(--radix-dropdown-menu-trigger-width) min-w-56"
        >
          <DropdownMenuLabel className="truncate">{me?.email}</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => go("/settings#profile")}>
            <User aria-hidden className="size-4" />
            Profile
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => go("/settings")}>
            <Settings aria-hidden className="size-4" />
            Settings
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuLabel>Appearance</DropdownMenuLabel>
          <DropdownMenuRadioGroup value={theme} onValueChange={(t) => setTheme(t as Theme)}>
            <DropdownMenuRadioItem value="light">Light</DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="dark">Dark</DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="system">System</DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => go("/help")}>
            <CircleHelp aria-hidden className="size-4" />
            Help and keyboard shortcuts
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => logout.mutate()}>
            <LogOut aria-hidden className="size-4" />
            Log out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
