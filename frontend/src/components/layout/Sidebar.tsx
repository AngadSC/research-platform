import { useState } from "react";
import { ChevronRight, ChevronsUpDown, Plus } from "lucide-react";
import { NavLink, useNavigate } from "react-router";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
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
import { useProjects } from "@/hooks/projects";
import { useLabs } from "@/hooks/workspace";
import type { Lab, Project } from "@/lib/api-types";
import { navItems, PROJECT_SECTIONS, type NavItem } from "@/lib/nav";
import { APP_NAME } from "@/lib/constants";
import { projectColorStyle } from "@/lib/projectColors";
import { cn } from "@/lib/utils";

/** A project row that opens into its sections. The project you are in opens by itself. */
function ProjectItem({
  labId,
  project,
  isCurrent,
  unread,
  onNavigate,
}: {
  labId: string;
  project: Project;
  isCurrent: boolean;
  unread: number;
  onNavigate: () => void;
}) {
  const [choice, setChoice] = useState<boolean>();
  const open = choice ?? isCurrent;
  const base = `/labs/${labId}/projects/${project.id}`;
  const listId = `project-sections-${project.id}`;
  return (
    <li style={projectColorStyle(project.color)}>
      <div className="flex items-center gap-0.5 rounded-md hover:bg-[color-mix(in_srgb,var(--project)_18%,transparent)]">
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
          <span className="truncate">{project.name}</span>
          <UnreadBadge count={unread} noun="message" className="ml-auto shrink-0" />
        </NavLink>
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
          {PROJECT_SECTIONS.map(({ to, label, icon: Icon }) => (
            <li key={to}>
              <NavLink to={`${base}/${to}`} className={linkClass} onClick={onNavigate}>
                <Icon aria-hidden />
                {label}
              </NavLink>
            </li>
          ))}
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
}: {
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
        className={`flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm font-semibold ${hoverTint} focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none`}
      >
        {loading ? (
          <Skeleton aria-label="Loading" className="h-4 w-32" />
        ) : (
          <span className="truncate">{current?.name ?? "Select a lab"}</span>
        )}
        <UnreadBadge count={unread} className="ml-auto" />
        <ChevronsUpDown className="size-4 shrink-0 opacity-60" aria-hidden />
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
  const { data: projects = [] } = useProjects(labId);
  const chatUnread = useUnreadChats(labId);
  const navigate = useNavigate();
  const current = labs.find((l) => l.id === labId);
  const unread = useUnreadCount(labId);
  const items = navItems(labId, current?.my_permissions, current?.inventory_enabled).filter(
    ({ to }) => to !== "/settings" && !to.endsWith("/notifications"), // both have their own menu
  );
  const adminItems = items.filter((item) => item.admin);
  const link = ({ to, label, icon: Icon, end }: NavItem) => (
    <NavLink key={to} to={to} end={end} className={linkClass} onClick={onClose}>
      <Icon aria-hidden />
      {label}
      {to.endsWith("/chat") && (
        <UnreadBadge count={chatUnread[LAB_CHAT] ?? 0} noun="message" className="ml-auto" />
      )}
    </NavLink>
  );
  return (
    <aside
      id="app-sidebar"
      className={cn(
        "w-64 shrink-0 flex-col gap-6 overflow-y-auto bg-sidebar p-4 print:hidden",
        // Below md the sidebar is a drawer that only exists while open.
        open
          ? "fixed inset-y-0 left-0 z-50 flex md:static md:z-auto"
          : desktopHidden
            ? "hidden"
            : "hidden md:flex",
      )}
    >
      <div>
        <div className="flex items-center justify-between px-2 pb-1">
          <p className="text-xs text-muted-foreground">{APP_NAME}</p>
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
        </div>
        <LabSwitcher
          labs={labs}
          current={current}
          loading={labsLoading}
          onNavigate={onClose}
          unread={unread}
        />
      </div>
      <PinnedNav onNavigate={onClose} />
      <nav aria-label="Main" className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-0.5">
        {items
          .filter((item) => !item.admin)
          .map((item) =>
            item.to.endsWith("/projects") ? (
              <div key={item.to} className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-0.5">
                <div className="flex items-center gap-0.5">
                  <NavLink
                    to={item.to}
                    end={item.end}
                    className={(s) => cn(linkClass(s), "min-w-0 flex-1")}
                    onClick={onClose}
                  >
                    <item.icon aria-hidden />
                    {item.label}
                  </NavLink>
                  {current?.my_permissions.includes("create_project") && (
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
                <ul className="ml-3 grid min-w-0 grid-cols-[minmax(0,1fr)] gap-0.5">
                  {projects.map((p) => (
                    <ProjectItem
                      key={p.id}
                      labId={labId!}
                      project={p}
                      isCurrent={p.id === projectId}
                      unread={chatUnread[p.id] ?? 0}
                      onNavigate={onClose}
                    />
                  ))}
                </ul>
              </div>
            ) : (
              link(item)
            ),
          )}
      </nav>
      {adminItems.length > 0 && (
        <nav aria-label="Admin" className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-0.5">
          <span className="px-2 pb-1 text-xs text-muted-foreground">Admin</span>
          {adminItems.map(link)}
        </nav>
      )}
      <SidebarFooter onNavigate={onClose} />
    </aside>
  );
}
