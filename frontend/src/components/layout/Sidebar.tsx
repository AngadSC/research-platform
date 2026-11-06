import { useState } from "react";
import { ChevronRight, ChevronsUpDown, LogOut, Plus } from "lucide-react";
import { NavLink, useNavigate } from "react-router";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { UnreadBadge, useUnreadCount } from "@/components/layout/UnreadBadge";
import { useLogout } from "@/hooks/auth";
import { useUnreadChats } from "@/hooks/chat";
import { useCurrentLabId, useCurrentProjectId } from "@/hooks/crumbs";
import { useProjects } from "@/hooks/projects";
import { useLabs } from "@/hooks/workspace";
import type { Lab, Project } from "@/lib/api-types";
import { navItems, PROJECT_SECTIONS } from "@/lib/nav";
import { APP_NAME } from "@/lib/constants";
import { cn } from "@/lib/utils";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex items-center gap-2 rounded-md px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none [&_svg]:size-4",
    isActive
      ? "bg-primary/10 font-semibold text-primary"
      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
  );

const iconButton =
  "shrink-0 rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none [&_svg]:size-4";

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
    <li>
      <div className="flex items-center gap-0.5 rounded-md hover:bg-accent">
        <NavLink
          to={base}
          onClick={() => {
            setChoice(true);
            onNavigate();
          }}
          className={cn(
            "flex min-w-0 flex-1 items-center gap-2 rounded-md px-3 py-2 text-sm hover:text-accent-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
            isCurrent ? "font-semibold text-foreground" : "text-muted-foreground",
          )}
        >
          <span className="truncate">{project.name}</span>
          {!open && <UnreadBadge count={unread} noun="message" className="ml-auto shrink-0" />}
        </NavLink>
        <button
          type="button"
          aria-label={`${project.name} sections`}
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => setChoice(!open)}
          className={iconButton}
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
                {to === "chat" && (
                  <UnreadBadge count={unread} noun="message" className="ml-auto shrink-0" />
                )}
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
  onNavigate,
  unread,
}: {
  labs: Lab[];
  current: Lab | undefined;
  onNavigate: () => void;
  unread: number;
}) {
  const navigate = useNavigate();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label="Switch lab"
        className="flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm font-semibold hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        <span className="truncate">{current?.name ?? "Select a lab"}</span>
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
            void navigate("/labs/new");
          }}
        >
          Create a lab
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: labs = [] } = useLabs();
  const labId = useCurrentLabId();
  const logout = useLogout();
  const projectId = useCurrentProjectId();
  const { data: projects = [] } = useProjects(labId);
  const chatUnread = useUnreadChats(labId);
  const navigate = useNavigate();
  const current = labs.find((l) => l.id === labId);
  const unread = useUnreadCount(labId);
  return (
    <aside
      id="app-sidebar"
      className={cn(
        "w-64 shrink-0 flex-col gap-6 overflow-y-auto bg-sidebar p-4 print:hidden",
        // Below md the sidebar is a drawer that only exists while open.
        open ? "fixed inset-y-0 left-0 z-50 flex md:static md:z-auto" : "hidden md:flex",
      )}
    >
      <div>
        <p className="px-2 pb-1 text-xs text-muted-foreground">{APP_NAME}</p>
        <LabSwitcher labs={labs} current={current} onNavigate={onClose} unread={unread} />
      </div>
      {labId && (
        <nav aria-label="Projects" className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-0.5">
          <div className="flex items-center justify-between px-2 pb-1">
            <span className="text-xs text-muted-foreground">Projects</span>
            {current?.my_permissions.includes("create_project") && (
              <button
                type="button"
                aria-label="New project"
                onClick={() => {
                  onClose();
                  void navigate(`/labs/${labId}?new=project`);
                }}
                className="rounded-md p-1 text-muted-foreground hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none [&_svg]:size-4"
              >
                <Plus aria-hidden />
              </button>
            )}
          </div>
          <ul className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-0.5">
            {projects.map((p) => (
              <ProjectItem
                key={p.id}
                labId={labId}
                project={p}
                isCurrent={p.id === projectId}
                unread={chatUnread[p.id] ?? 0}
                onNavigate={onClose}
              />
            ))}
          </ul>
        </nav>
      )}
      <nav aria-label="Main" className="grid gap-0.5">
        {navItems(labId, current?.my_permissions).map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={linkClass} onClick={onClose}>
            <Icon aria-hidden />
            {label}
            {to.endsWith("/notifications") && <UnreadBadge count={unread} className="ml-auto" />}
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
    </aside>
  );
}
