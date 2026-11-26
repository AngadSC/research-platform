import { useRef, useState } from "react";
import {
  ChevronRight,
  Building2,
  ChevronsUpDown,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  SlidersHorizontal,
  Star,
} from "lucide-react";
import { NavLink, useLocation, useNavigate } from "react-router";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { applyOrder } from "@/components/layout/holdToReorder";
import {
  groupLabel,
  hoverTint,
  iconButton,
  linkClass,
  PinnedNav,
  SidebarFooter,
} from "@/components/layout/SidebarSections";
import { UnreadBadge, useUnreadCount } from "@/components/layout/UnreadBadge";
import { Skeleton } from "@/components/ui/skeleton";
import { LAB_CHAT, useUnreadChats } from "@/hooks/chat";
import { useCurrentLabId, useCurrentProjectId } from "@/hooks/crumbs";
import { useLayout, usePins, useSidebarOrder } from "@/hooks/preferences";
import { useMyTasks, useProjects } from "@/hooks/projects";
import { localDateISO } from "@/lib/format";
import { isSnoozed } from "@/lib/snooze";
import { useLabs } from "@/hooks/workspace";
import type { Lab, Project } from "@/lib/api-types";
import { navItems, projectSections, type NavItem } from "@/lib/nav";
import { APP_NAME } from "@/lib/constants";
import { projectColorStyle } from "@/lib/projectColors";
import { cn } from "@/lib/utils";

/** The lab part of a link, so one saved order fits every lab. */
const keyOf = (to: string) => to.replace(/^\/labs\/[^/]+\//, "");

/** A group heading that folds its links away. The choice is kept in this browser. */
function useFolded(key: string) {
  const [folded, setFolded] = useState(() => {
    try {
      return localStorage.getItem(`sidebar-folded-${key}`) === "1";
    } catch {
      return false;
    }
  });
  const toggle = () => {
    setFolded(!folded);
    try {
      localStorage.setItem(`sidebar-folded-${key}`, folded ? "0" : "1");
    } catch {
      // storage is blocked: the choice lasts until the page reloads
    }
  };
  return [folded, toggle] as const;
}

function GroupHeading({
  label,
  folded,
  onToggle,
}: {
  label: string;
  folded: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      aria-expanded={!folded}
      aria-label={`${label} group`}
      onClick={onToggle}
      className={cn(
        groupLabel,
        "flex w-full items-center justify-between rounded-md text-left hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
      )}
    >
      {label}
      <ChevronRight
        aria-hidden
        className={cn("size-3 transition-transform", !folded && "rotate-90")}
      />
    </button>
  );
}

/** The lab's pages that live in a group of their own, not in the main list. */
const LAB_GROUP = [
  "members",
  "training",
  "papers",
  "documents",
  "participants",
  "settings/integrations",
];
const ADMIN_GROUP = [
  "inventory",
  "samples",
  "monitoring",
  "ethics",
  "funding",
  "retention",
  "audit-log",
  "admin",
];

/**
 * Icons-only sidebar: a group of pages behind one icon, below the divider. Hovering (or clicking, or focusing) it opens
 * a small menu of its pages, like a project does in the icons-only sidebar.
 */
function GroupFlyout({
  label,
  icon: Icon,
  items,
  slim,
  onNavigate,
}: {
  label: string;
  icon: NavItem["icon"];
  items: NavItem[];
  slim: boolean;
  onNavigate: () => void;
}) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const timer = useRef<number>(0);
  const show = () => {
    window.clearTimeout(timer.current);
    setOpen(true);
  };
  const hide = () => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(false), 160);
  };
  const here = items.some((i) => pathname === i.to || pathname.startsWith(`${i.to}/`));
  return (
    <DropdownMenu open={open} onOpenChange={setOpen} modal={false}>
      <DropdownMenuTrigger
        aria-label={`${label}, pages`}
        title={slim ? label : undefined}
        onPointerEnter={show}
        onPointerLeave={hide}
        // hovering already opened it: a click must keep it open, not toggle it shut
        onPointerDown={(e) => {
          e.preventDefault();
          show();
        }}
        className={cn(
          "flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none [&_svg]:size-4",
          here && "font-medium text-foreground",
          slim && "justify-center px-0",
        )}
      >
        <Icon aria-hidden />
        {slim ? <span className="sr-only">{label}</span> : label}
        {!slim && <ChevronRight aria-hidden className="ml-auto size-3.5 opacity-60" />}
      </DropdownMenuTrigger>
      <DropdownMenuContent
        side="right"
        align="end"
        sideOffset={10}
        onPointerEnter={show}
        onPointerLeave={hide}
        onCloseAutoFocus={(e) => e.preventDefault()}
        className="w-52"
      >
        <DropdownMenuLabel className="font-semibold text-foreground">{label}</DropdownMenuLabel>
        {items.map(({ to, label: name, icon: ItemIcon }) => (
          <DropdownMenuItem
            key={to}
            onSelect={() => {
              onNavigate();
              void navigate(to);
            }}
          >
            <ItemIcon aria-hidden className="size-4" />
            {name}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Icons-only sidebar: a project is one coloured initial. Hovering (or focusing) it opens a small
 * menu of its pages, so you can go straight to Tasks, Notebook, Documents and the rest. */
function SlimProject({
  labId,
  project,
  isCurrent,
  overdue = 0,
  onNavigate,
}: {
  labId: string;
  project: Project;
  isCurrent: boolean;
  overdue?: number;
  onNavigate: () => void;
}) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const timer = useRef<number>(0);
  const base = `/labs/${labId}/projects/${project.id}`;
  const show = () => {
    window.clearTimeout(timer.current);
    setOpen(true);
  };
  const hide = () => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(false), 160);
  };
  return (
    <li style={projectColorStyle(project.color)}>
      <DropdownMenu open={open} onOpenChange={setOpen} modal={false}>
        <DropdownMenuTrigger
          aria-label={`${project.name}, pages`}
          onPointerEnter={show}
          onPointerLeave={hide}
          onClick={() => {
            setOpen(false);
            onNavigate();
            void navigate(`${base}/overview`);
          }}
          className={cn(
            "relative grid size-8 place-items-center rounded-lg text-xs font-semibold text-(--project) hover:bg-[color-mix(in_srgb,var(--project)_18%,transparent)] focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
            isCurrent && "bg-[color-mix(in_srgb,var(--project)_22%,transparent)]",
          )}
        >
          {project.name.slice(0, 1).toUpperCase()}
          <UnreadBadge count={overdue} noun="overdue task" className="absolute -top-1 -right-1" />
        </DropdownMenuTrigger>
        <DropdownMenuContent
          side="right"
          align="start"
          sideOffset={10}
          onPointerEnter={show}
          onPointerLeave={hide}
          onCloseAutoFocus={(e) => e.preventDefault()}
          className="w-56"
        >
          <DropdownMenuLabel className="flex items-center gap-2 font-semibold text-foreground">
            <span
              aria-hidden
              className="size-2.5 rounded-full bg-(--project)"
              style={projectColorStyle(project.color)}
            />
            <span className="truncate" title={project.name}>
              {project.name}
            </span>
          </DropdownMenuLabel>
          {projectSections(project.study_types).map(({ to, label, icon: Icon }) => (
            <DropdownMenuItem
              key={to}
              onSelect={() => {
                onNavigate();
                void navigate(`${base}/${to}`);
              }}
            >
              <Icon aria-hidden className="size-4" />
              {label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </li>
  );
}

/** A project row that opens into its sections. The project you are in opens by itself. */
function ProjectItem({
  labId,
  project,
  isCurrent,
  unread,
  overdue = 0,
  onNavigate,
}: {
  labId: string;
  project: Project;
  isCurrent: boolean;
  unread: number;
  /** Your own overdue tasks in this project. */
  overdue?: number;
  onNavigate: () => void;
}) {
  const { pins, toggle: togglePin } = usePins();
  const [choice, setChoice] = useState<boolean>();
  const open = choice ?? isCurrent;
  const base = `/labs/${labId}/projects/${project.id}`;
  const listId = `project-sections-${project.id}`;
  const pinned = pins.some((p) => p.url === base);
  return (
    <li style={projectColorStyle(project.color)}>
      <div className="group/row flex items-center gap-0.5 rounded-md hover:bg-[color-mix(in_srgb,var(--project)_18%,transparent)]">
        <NavLink
          to={base}
          onClick={() => {
            setChoice(true);
            onNavigate();
          }}
          className={cn(
            "flex min-w-0 flex-1 items-center gap-2 rounded-md px-3 py-2 text-sm hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
            isCurrent ? "font-semibold text-foreground" : "text-muted-foreground",
          )}
        >
          <span aria-hidden className="size-2.5 shrink-0 rounded-full bg-(--project)" />
          <span className="line-clamp-2 min-w-0 break-words" title={project.name}>
            {project.name}
          </span>
          {project.status === "archived" && (
            <span className="shrink-0 rounded bg-muted px-1 text-[10px] font-normal text-muted-foreground">
              Archived
            </span>
          )}
          <UnreadBadge count={overdue} noun="overdue task" className="ml-auto shrink-0" />
          <UnreadBadge count={unread} noun="message" className="shrink-0" />
        </NavLink>
        <button
          type="button"
          aria-label={pinned ? `Unpin ${project.name}` : `Pin ${project.name}`}
          aria-pressed={pinned}
          onClick={() => togglePin({ url: base, label: project.name })}
          className={cn(
            iconButton,
            "hover:bg-transparent",
            !pinned && "md:opacity-0 md:group-hover/row:opacity-100 focus-visible:opacity-100",
            pinned && "text-warning-text",
          )}
        >
          <Star aria-hidden className={cn(pinned && "fill-current")} />
        </button>
        <button
          type="button"
          aria-label={`${project.name} sections`}
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => setChoice(!open)}
          className={cn(iconButton, "hover:bg-transparent")}
        >
          <ChevronRight aria-hidden className={cn("transition-transform", open && "rotate-90")} />
        </button>
      </div>
      {open && (
        <ul id={listId} className="mt-0.5 ml-3 grid grid-cols-1 gap-0.5 border-l pl-2">
          {projectSections(project.study_types).map((section) => {
            const { to, label, icon: Icon } = section;
            const hint = (section as { hint?: string }).hint;
            return (
              <li key={to}>
                <NavLink
                  to={`${base}/${to}`}
                  className={(s) =>
                    cn(
                      linkClass(s),
                      // The section you are on wears the project's own colour.
                      s.isActive && "text-(--project) before:bg-(--project)",
                      !s.isActive && "hover:bg-[color-mix(in_srgb,var(--project)_14%,transparent)]",
                    )
                  }
                  onClick={onNavigate}
                  title={hint}
                  aria-description={hint}
                >
                  <Icon aria-hidden />
                  {label}
                </NavLink>
              </li>
            );
          })}
        </ul>
      )}
    </li>
  );
}

function LabSwitcher({
  labs,
  current,
  loading,
  onNavigate,
  unread,
  slim = false,
}: {
  slim?: boolean;
  labs: Lab[];
  current: Lab | undefined;
  loading: boolean;
  onNavigate: () => void;
  unread: number;
}) {
  const navigate = useNavigate();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label="Switch lab"
        title={slim ? (current?.name ?? "Switch lab") : undefined}
        className={`flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm font-semibold ${hoverTint} focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none ${slim ? "justify-center px-0" : ""}`}
      >
        {slim ? (
          <span className="relative grid size-8 place-items-center rounded-lg bg-primary/15 text-primary">
            {(current?.name ?? "?").slice(0, 1).toUpperCase()}
            <UnreadBadge count={unread} className="absolute -top-1 -right-1" />
          </span>
        ) : loading ? (
          <Skeleton aria-label="Loading" className="h-4 w-32" />
        ) : (
          <span className="truncate" title={current?.name}>
            {current?.name ?? "Select a lab"}
          </span>
        )}
        {!slim && <UnreadBadge count={unread} className="ml-auto" />}
        {!slim && <ChevronsUpDown className="size-4 shrink-0 opacity-60" aria-hidden />}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <DropdownMenuLabel>Switch lab</DropdownMenuLabel>
        {labs.map((lab) => (
          <DropdownMenuItem
            key={lab.id}
            onSelect={() => {
              onNavigate();
              void navigate(`/labs/${lab.id}`);
            }}
          >
            {lab.name}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => {
            onNavigate();
            void navigate("/labs");
          }}
        >
          All labs
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={() => {
            onNavigate();
            void navigate("/labs/new");
          }}
        >
          Create a lab
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function Sidebar({
  open,
  desktopHidden,
  onClose,
}: {
  open: boolean;
  /** md and up: the user tucked the sidebar away. The drawer below md ignores this. */
  desktopHidden: boolean;
  onClose: () => void;
}) {
  const { data: labs = [], isLoading: labsLoading } = useLabs();
  const labId = useCurrentLabId();
  const projectId = useCurrentProjectId();
  const { data: fetched = [] } = useProjects(labId);
  // Active work first: archived projects drop to the bottom (the sort is stable).
  const projects = [...fetched].sort(
    (a, b) => Number(a.status === "archived") - Number(b.status === "archived"),
  );
  const chatUnread = useUnreadChats(labId);
  const navigate = useNavigate();
  const current = labs.find((l) => l.id === labId);
  const unread = useUnreadCount(labId);
  const today = localDateISO();
  const lateTasks = (useMyTasks(labId ?? "").data ?? []).filter(
    (t) => t.due_date && t.due_date < today && !isSnoozed(t.snoozed_until),
  );
  const overdueMine = lateTasks.length;
  const lateIn = (id: string) => lateTasks.filter((t) => t.project === id).length;
  const done = projects.filter((p) => p.status === "completed" && p.id !== projectId);
  const layout = useLayout();
  const slim = layout.compact && !open; // the drawer below md always shows words
  const items = navItems(labId, current?.my_permissions, current?.inventory_enabled).filter(
    ({ to }) =>
      to !== "/settings" &&
      to !== "/help" &&
      !to.endsWith("/notifications") && // each has its own menu
      !layout.hidden.includes(keyOf(to)),
  );
  const order = useSidebarOrder();
  const [labFolded, toggleLab] = useFolded("lab");
  const [peopleFolded, togglePeople] = useFolded("people");
  const [adminFolded, toggleAdmin] = useFolded("admin");
  const grouped = (keys: string[]) =>
    keys.flatMap((k) => items.filter((i) => keyOf(i.to) === k || keyOf(i.to) === `${k}/`));
  const labGroup = grouped(LAB_GROUP);
  const adminGroup = grouped(ADMIN_GROUP);
  const inGroup = new Set([...labGroup, ...adminGroup].map((i) => i.to));
  const mainItems = applyOrder(
    items.filter((item) => !inGroup.has(item.to) && !item.admin),
    (i) => keyOf(i.to),
    order.main,
  );
  const badgeAt = slim ? "absolute top-0 right-1" : "ml-auto";
  const link = ({ to, label, icon: Icon, end }: NavItem) => (
    <NavLink
      key={to}
      to={to}
      end={end}
      title={slim ? label : undefined}
      className={(st) => cn(linkClass(st), slim && "justify-center px-0")}
      onClick={onClose}
    >
      <Icon aria-hidden />
      {slim ? <span className="sr-only">{label}</span> : label}
      {to.endsWith("/my-work") && (
        <UnreadBadge count={overdueMine} noun="overdue task" className={badgeAt} />
      )}
      {to.endsWith("/chat") && (
        <UnreadBadge count={chatUnread[LAB_CHAT] ?? 0} noun="message" className={badgeAt} />
      )}
    </NavLink>
  );
  return (
    <aside
      id="app-sidebar"
      data-drawer={open ? "open" : undefined}
      className={cn(
        "glass glass--solid shrink-0 flex-col gap-4 overflow-hidden rounded-none border-0 border-r bg-sidebar shadow-none print:hidden",
        slim ? "w-[4.5rem] p-2" : "w-72 p-4",
        // Below md the sidebar is a drawer that only exists while open.
        open
          ? "fixed inset-y-0 left-0 z-50 flex md:static md:z-auto"
          : desktopHidden
            ? "hidden"
            : "hidden md:flex",
      )}
    >
      <div>
        <div
          className={cn("flex items-center pb-1", slim ? "flex-col gap-2" : "justify-between px-2")}
        >
          {/* Light theme: the original logo. Dark theme (chosen, or the system's): the dark logo
              and a light wordmark. The `dark` class is set for both, so it switches by itself. */}
          <span className="inline-flex h-8 items-center">
            <img
              src={slim ? "/logo.png" : "/logo-full.png"}
              alt={APP_NAME}
              className={cn("w-auto dark:hidden", slim ? "h-8" : "h-7")}
            />
            <span className="hidden items-center gap-2 dark:inline-flex">
              <img src="/logo-dark.png" alt={slim ? APP_NAME : ""} className="h-8 w-auto" />
              {!slim && (
                <span className="text-lg font-bold tracking-tight">
                  <span className="text-foreground">lab</span>
                  <span className="text-[#16a34a]">benchos</span>
                </span>
              )}
            </span>
          </span>
          <span className="flex items-center gap-0.5">
            {!slim && (
              <button
                type="button"
                aria-label="Create a lab"
                onClick={() => {
                  onClose();
                  void navigate("/labs/new");
                }}
                className={iconButton}
              >
                <Plus aria-hidden />
              </button>
            )}
            {!open && (
              <button
                type="button"
                aria-label={slim ? "Show sidebar labels" : "Show icons only"}
                title={slim ? "Show labels" : "Icons only"}
                onClick={() => layout.setCompact(!layout.compact)}
                className={iconButton}
              >
                {slim ? <PanelLeftOpen aria-hidden /> : <PanelLeftClose aria-hidden />}
              </button>
            )}
          </span>
        </div>
        <LabSwitcher
          labs={labs}
          current={current}
          loading={labsLoading}
          onNavigate={onClose}
          unread={unread}
          slim={slim}
        />
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto [mask-image:linear-gradient(to_bottom,black_calc(100%-1.5rem),transparent)]">
        {!slim && <PinnedNav onNavigate={onClose} />}
        {labId && !current ? (
          <div aria-busy="true" aria-label="Loading navigation" className="grid gap-2 px-3">
            {Array.from({ length: 8 }, (_, i) => (
              <Skeleton key={i} className="h-5 w-full" />
            ))}
          </div>
        ) : (
          <>
            <nav aria-label="Main" className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-0.5">
              {slim ? (
                <hr aria-hidden className="mx-2 border-border" />
              ) : (
                <GroupHeading label="Work" folded={labFolded} onToggle={toggleLab} />
              )}
              {(slim || !labFolded) &&
                mainItems.map((item) => (
                  <div key={item.to} className="min-w-0">
                    {item.to.endsWith("/projects") ? (
                      <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-0.5">
                        <div className="flex items-center gap-0.5">
                          <NavLink
                            to={item.to}
                            end={item.end}
                            title={slim ? item.label : undefined}
                            className={(s) =>
                              cn(linkClass(s), "min-w-0 flex-1", slim && "justify-center px-0")
                            }
                            onClick={onClose}
                          >
                            <item.icon aria-hidden />
                            {slim ? <span className="sr-only">{item.label}</span> : item.label}
                          </NavLink>
                          {!slim && current?.my_permissions.includes("create_project") && (
                            <button
                              type="button"
                              aria-label="New project"
                              onClick={() => {
                                onClose();
                                void navigate(`${item.to}?new=project`);
                              }}
                              className={iconButton}
                            >
                              <Plus aria-hidden />
                            </button>
                          )}
                        </div>
                        {slim ? (
                          <ul className="grid justify-items-center gap-1">
                            {projects
                              .filter((p) => p.status !== "completed" || p.id === projectId)
                              .map((p) => (
                                <SlimProject
                                  key={p.id}
                                  labId={labId!}
                                  project={p}
                                  isCurrent={p.id === projectId}
                                  overdue={lateIn(p.id)}
                                  onNavigate={onClose}
                                />
                              ))}
                          </ul>
                        ) : (
                          <ul className="ml-3 grid min-w-0 grid-cols-[minmax(0,1fr)] gap-0.5">
                            {projects
                              .filter((p) => p.status !== "completed" || p.id === projectId)
                              .map((p) => (
                                <ProjectItem
                                  key={p.id}
                                  labId={labId!}
                                  project={p}
                                  isCurrent={p.id === projectId}
                                  unread={chatUnread[p.id] ?? 0}
                                  overdue={lateIn(p.id)}
                                  onNavigate={onClose}
                                />
                              ))}
                            {done.length > 0 && (
                              <li>
                                <details>
                                  <summary className="cursor-pointer rounded-md px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground">
                                    Completed ({done.length})
                                  </summary>
                                  <ul className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-0.5">
                                    {done.map((p) => (
                                      <ProjectItem
                                        key={p.id}
                                        labId={labId!}
                                        project={p}
                                        isCurrent={false}
                                        unread={chatUnread[p.id] ?? 0}
                                        overdue={lateIn(p.id)}
                                        onNavigate={onClose}
                                      />
                                    ))}
                                  </ul>
                                </details>
                              </li>
                            )}
                          </ul>
                        )}
                      </div>
                    ) : (
                      link(item)
                    )}
                  </div>
                ))}
              {!slim && order.main.length > 0 && (
                <button
                  type="button"
                  onClick={order.reset}
                  className="mt-1 self-start rounded px-3 text-xs text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  Reset order
                </button>
              )}
            </nav>
            {(labGroup.length > 0 || adminGroup.length > 0) && (
              <nav
                aria-label="Lab and admin"
                className={cn(
                  "grid min-w-0 grid-cols-[minmax(0,1fr)] gap-0.5 border-t",
                  slim ? "pt-2" : "pt-3",
                )}
              >
                {[
                  {
                    label: "Lab",
                    icon: Building2,
                    items: labGroup,
                    folded: peopleFolded,
                    toggle: togglePeople,
                  },
                  {
                    label: adminGroup.some((i) => i.admin) ? "Admin" : "Lab resources",
                    icon: SlidersHorizontal,
                    items: adminGroup,
                    folded: adminFolded,
                    toggle: toggleAdmin,
                  },
                ]
                  .filter((g) => g.items.length > 0)
                  .map((g) =>
                    slim ? (
                      <GroupFlyout
                        key={g.label}
                        label={g.label}
                        icon={g.icon}
                        items={g.items}
                        slim
                        onNavigate={onClose}
                      />
                    ) : (
                      <div key={g.label} className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-0.5">
                        <GroupHeading label={g.label} folded={g.folded} onToggle={g.toggle} />
                        {!g.folded && g.items.map(link)}
                      </div>
                    ),
                  )}
              </nav>
            )}
          </>
        )}
      </div>
      <SidebarFooter onNavigate={onClose} role={current?.my_role} slim={slim} />
    </aside>
  );
}
