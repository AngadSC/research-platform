import { MobileTabBar } from "@/components/layout/MobileTabBar";
import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import { Menu, PanelLeft, Pin, PinOff, Plus, Search } from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { Breadcrumbs, type Crumb } from "@/components/shared/Breadcrumbs";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/sonner";
import { useIncomingBanners } from "@/hooks/banners";
import { useUnreadChats } from "@/hooks/chat";
import { useCurrentProjectId, useCrumbs, useCurrentLabId } from "@/hooks/crumbs";
import {
  useGlass,
  useLayout,
  usePins,
  useRecents,
  useSyncTimeZone,
  useTrackRecent,
} from "@/hooks/preferences";
import { useProjects } from "@/hooks/projects";
import { useLabs } from "@/hooks/workspace";
import { useRegisterCommands, type Command } from "@/lib/commands";
import { CommandPalette } from "./CommandPalette";
import { navItems } from "@/lib/nav";
import { shortcutId } from "@/lib/layout";
import { APP_NAME, MOD_KEY, OPEN_QUICK_CAPTURE_EVENT, OPEN_SEARCH_EVENT } from "@/lib/constants";
import { useMe } from "@/hooks/workspace";
import { useAccountTheme } from "@/lib/theme";
import { AssistantDrawer } from "@/components/assistant/AssistantDrawer";
import { NamePrompt } from "./NamePrompt";
import { GoogleEditorHost } from "@/components/shared/GoogleEditorPanel";
import { QuickCapture } from "./QuickCapture";
import { greeting } from "@/lib/greeting";
import { WeatherChip } from "./WeatherChip";
import { NotificationBell } from "./NotificationBell";
import { Sidebar } from "./Sidebar";
import { Tutorial } from "./Tutorial";

const SIDEBAR_KEY = "sidebar-hidden";

function readSidebarHidden() {
  try {
    return localStorage.getItem(SIDEBAR_KEY) === "1";
  } catch {
    return false; // storage is blocked: the sidebar just starts open
  }
}

/** A page's pin name: its own, after the project or document it sits in. */
function pinLabel(crumbs: Crumb[]) {
  const last = crumbs.at(-1)?.label ?? "";
  const owner = crumbs.filter((c) => c.kind).at(-1);
  return owner && owner !== crumbs.at(-1) ? `${owner.label} · ${last}` : last;
}

function PinButton({ crumbs }: { crumbs: Crumb[] }) {
  const { pathname } = useLocation();
  const { pins, toggle } = usePins();
  if (crumbs.length === 0) return null;
  const pinned = pins.some((p) => p.url === pathname);
  const Icon = pinned ? PinOff : Pin;
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={pinned ? "Unpin this page" : "Pin this page"}
      aria-pressed={pinned}
      disabled={crumbs.some((c) => c.pending)}
      onClick={() => toggle({ url: pathname, label: pinLabel(crumbs) })}
    >
      <Icon aria-hidden />
    </Button>
  );
}

/** "Tasks · Pilot Attention Study · labbenchos", from the breadcrumb trail. */
// eslint-disable-next-line react-refresh/only-export-components
export function pageTitle(crumbs: Crumb[]) {
  const loaded = crumbs.filter((c) => !c.pending);
  return loaded.length === crumbs.length && crumbs.length > 0
    ? `${pinLabel(crumbs)} · ${APP_NAME}`
    : APP_NAME;
}

export function AppShell() {
  const navigate = useNavigate();
  const crumbs = useCrumbs();
  useTrackRecent(crumbs);
  const recents = useRecents();
  const title = pageTitle(crumbs);
  useEffect(() => {
    document.title = title;
  }, [title]);
  const labId = useCurrentLabId();
  const { data: labs } = useLabs();
  const { data: projects } = useProjects(labId);
  const projectId = useCurrentProjectId();
  const projectColor = projects?.find((p) => p.id === projectId)?.color;
  // Inside a project, its colour themes the whole page: background, accents and headings.
  useEffect(() => {
    const el = document.documentElement;
    if (projectColor) {
      el.dataset.projectTheme = projectColor;
      el.style.setProperty("--project", `var(--project-${projectColor})`);
    }
    return () => {
      delete el.dataset.projectTheme;
      el.style.removeProperty("--project");
    };
  }, [projectColor]);
  const hasUnread = Object.keys(useUnreadChats(labId)).length > 0;
  const [navOpen, setNavOpen] = useState(false);
  const [sidebarHidden, setSidebarHidden] = useState(readSidebarHidden);
  const toggleSidebar = () => {
    setSidebarHidden(!sidebarHidden);
    try {
      localStorage.setItem(SIDEBAR_KEY, sidebarHidden ? "0" : "1");
    } catch {
      // storage is blocked: the choice lasts until the page reloads
    }
  };
  const me = useMe().data as { preferences?: unknown; display_name?: string } | undefined;
  useAccountTheme(me?.preferences);
  const name = me?.display_name ?? "";
  useSyncTimeZone();
  useGlass(); // applies the saved look (glass or reduced glass)

  // Below md the sidebar is a drawer: Escape closes it.
  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setNavOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [navOpen]);

  useIncomingBanners(labId);
  const layout = useLayout();
  const { pins } = usePins();
  const labPerms = labs?.find((l) => l.id === labId);
  const shortcuts = navItems(labId, labPerms?.my_permissions, labPerms?.inventory_enabled).filter(
    (n) => n.to !== "/settings" && !n.to.endsWith("/notifications"),
  );
  const barParts: Record<string, ReactNode> = {
    greeting: name ? (
      <span className="hidden truncate text-sm font-medium text-muted-foreground md:inline">
        {greeting(new Date(), name)}
      </span>
    ) : null,
    pin: <PinButton crumbs={crumbs} />,
    pins: pins.length > 0 && (
      <span className="hidden min-w-0 items-center gap-1 lg:flex">
        {pins.slice(0, 4).map((p) => (
          <Button key={p.url} variant="ghost" size="sm" asChild className="max-w-36">
            <NavLink to={p.url} title={p.label}>
              <span className="truncate">{p.label}</span>
            </NavLink>
          </Button>
        ))}
      </span>
    ),
    search: (
      <Button
        variant="secondary"
        size="sm"
        aria-label="Search"
        onClick={() => window.dispatchEvent(new Event(OPEN_SEARCH_EVENT))}
      >
        <Search aria-hidden />
        <span className="hidden sm:inline">Search</span>
        <kbd className="hidden rounded bg-background px-1.5 text-xs font-medium text-muted-foreground sm:inline">
          {MOD_KEY} K
        </kbd>
      </Button>
    ),
    task: labId && (
      <Button
        variant="outline"
        size="sm"
        aria-label="Add a task"
        title={`Add a task (${MOD_KEY} G)`}
        onClick={() => window.dispatchEvent(new Event(OPEN_QUICK_CAPTURE_EVENT))}
      >
        <Plus aria-hidden />
        <span className="hidden sm:inline">Task</span>
      </Button>
    ),
    assistant: labId && <AssistantDrawer labId={labId} />,
    weather: <WeatherChip />,
    bell: labId && <NotificationBell labId={labId} />,
    ...Object.fromEntries(
      shortcuts.map((n) => [
        shortcutId(n.to),
        <Button key={n.to} variant="ghost" size="icon" asChild className="hidden md:inline-flex">
          <NavLink to={n.to} end={n.end} aria-label={n.label} title={n.label}>
            <n.icon aria-hidden />
          </NavLink>
        </Button>,
      ]),
    ),
  };
  const barOrder = layout.topbar;

  const commands = useMemo<Command[]>(
    () => [
      ...navItems(
        labId,
        labs?.find((l) => l.id === labId)?.my_permissions,
        labs?.find((l) => l.id === labId)?.inventory_enabled,
      ).map((n) => ({
        id: `nav:${n.to}`,
        label: `Go to ${n.label}`,
        group: "Navigate",
        icon: n.icon,
        onSelect: () => void navigate(n.to),
      })),
      ...(projects ?? []).map((p) => ({
        id: `project:${p.id}`,
        label: `Go to project ${p.name}`,
        group: "Projects",
        onSelect: () => void navigate(`/labs/${labId}/projects/${p.id}`),
      })),
      ...(labs ?? []).map((l) => ({
        id: `lab:${l.id}`,
        label: `Switch to ${l.name}`,
        group: "Labs",
        onSelect: () => void navigate(`/labs/${l.id}`),
      })),
      {
        id: "lab:new",
        label: "Create a lab",
        group: "Labs",
        onSelect: () => void navigate("/labs/new"),
      },
    ],
    [navigate, labId, labs, projects],
  );
  useRegisterCommands(commands);

  return (
    <TooltipProvider>
      <a
        href="#main"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("main")?.focus();
        }}
        className="sr-only z-[100] rounded-md bg-background px-3 py-2 text-sm font-medium shadow focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        Skip to main content
      </a>
      <NamePrompt />
      <div className="flex h-screen text-foreground md:pr-[calc(var(--assistant-w,0px)+var(--google-w,0px))] print:block print:h-auto print:pr-0">
        <Sidebar open={navOpen} desktopHidden={sidebarHidden} onClose={() => setNavOpen(false)} />
        {navOpen && (
          <div
            aria-hidden
            className="fixed inset-0 z-40 bg-black/40 md:hidden"
            onClick={() => setNavOpen(false)}
          />
        )}
        <div className="relative flex min-w-0 flex-1 flex-col">
          <header className="glass glass--strong absolute inset-x-3 top-3 z-30 flex items-center gap-2 rounded-2xl px-3 py-2 print:hidden md:inset-x-5">
            <Button
              variant="ghost"
              size="icon"
              className="relative md:hidden"
              aria-label={hasUnread ? "Open navigation, unread messages" : "Open navigation"}
              aria-controls="app-sidebar"
              aria-expanded={navOpen}
              onClick={() => setNavOpen(true)}
            >
              <Menu aria-hidden />
              {hasUnread && (
                <span
                  aria-hidden
                  className="absolute top-1.5 right-1.5 size-2.5 rounded-full bg-danger ring-2 ring-background"
                />
              )}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="hidden md:inline-flex"
              aria-label={sidebarHidden ? "Show sidebar" : "Hide sidebar"}
              aria-controls="app-sidebar"
              aria-expanded={!sidebarHidden}
              onClick={toggleSidebar}
            >
              <PanelLeft aria-hidden />
            </Button>
            <span className="text-sm font-semibold md:hidden">{APP_NAME}</span>
            {barOrder.map((id, i) => {
              const part = barParts[id];
              if (!part) return null;
              // Everything after the greeting sits to the right.
              const first = barOrder.findIndex((x) => barParts[x] && x !== "greeting") === i;
              return (
                <Fragment key={id}>
                  {first && <span className="flex-1" />}
                  {part}
                </Fragment>
              );
            })}
          </header>
          <main
            id="main"
            tabIndex={-1}
            className="@container outline-none min-h-0 flex-1 overflow-y-auto pt-[4.75rem] pb-20 md:pb-0 print:overflow-visible print:pt-0"
          >
            <div className="px-4 py-4 md:px-8 print:px-0">
              <div className="mb-4 print:hidden">
                <Breadcrumbs items={crumbs} />
              </div>
              <Outlet />
            </div>
          </main>
        </div>
      </div>
      <MobileTabBar labId={labId} onMore={() => setNavOpen(true)} />
      <QuickCapture />
      <GoogleEditorHost />
      <CommandPalette labId={labId} recents={recents} onGo={(url) => void navigate(url)} />
      <Tutorial />
      <Toaster position="top-center" />
    </TooltipProvider>
  );
}
