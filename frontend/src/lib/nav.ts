import {
  Archive,
  Bell,
  BookOpen,
  Boxes,
  Building2,
  CalendarDays,
  CheckSquare,
  CircleHelp,
  FileText,
  FolderKanban,
  GraduationCap,
  History,
  LayoutDashboard,
  Home,
  ListChecks,
  MessagesSquare,
  Plug,
  Presentation,
  Settings,
  ShieldCheck,
  Users,
  Workflow,
  type LucideIcon,
} from "lucide-react";

/** The sections of a project: a dropdown in the sidebar, and tabs below md. */
export const PROJECT_SECTIONS = [
  { to: "overview", label: "Overview", icon: LayoutDashboard },
  { to: "tasks", label: "Tasks", icon: CheckSquare },
  { to: "documents", label: "Documents and files", icon: FileText },
  {
    to: "workflow",
    label: "Workflow",
    icon: Workflow,
    hint: "Funding, ethics, participants, data, analysis, manuscript and review",
  },
  { to: "external", label: "Posters and talks", icon: Presentation },
] as const;

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end: boolean;
  /** Only shown in the sidebar's Admin group. */
  admin?: boolean;
}

/** Sidebar and palette links. Lab pages only appear once a lab is selected. */
export function navItems(
  labId?: string,
  permissions: string[] = [],
  inventoryEnabled = true,
): NavItem[] {
  const settings: NavItem = { to: "/settings", label: "Settings", icon: Settings, end: false };
  const help: NavItem = { to: "/help", label: "Help", icon: CircleHelp, end: false };
  if (!labId) return [{ to: "/", label: "Home", icon: Home, end: true }, help, settings];
  const can = (perm: string) => permissions.includes(perm);
  const page = (path: string, label: string, icon: LucideIcon, admin?: boolean): NavItem => ({
    to: `/labs/${labId}/${path}`,
    label,
    icon,
    end: path === "dashboard" || path === "projects",
    admin,
  });
  return [
    page("dashboard", "Home", Home),
    page("projects", "Projects", FolderKanban),
    page("my-work", "My work", ListChecks),
    page("members", "Members", Users),
    ...(inventoryEnabled ? [page("inventory", "Inventory", Boxes)] : []), // D227: wet labs only
    page("training", "Training", GraduationCap),
    ...(can("view_ethics") ? [page("ethics", "Ethics", ShieldCheck)] : []),
    page("documents", "Lab documents", FileText),
    page("calendar", "Calendar", CalendarDays),
    page("chat", "Lab chat", MessagesSquare),
    page("papers", "Papers", BookOpen),
    page("settings/integrations", "Integrations", Plug), // everyone connects their own accounts
    page("notifications", "Notifications", Bell), // the palette only; the sidebar has the bell
    // These three permissions are held by PIs and lab admins only.
    ...(can("view_audit_log") ? [page("audit-log", "Audit log", History, true)] : []),
    ...(can("view_retention") ? [page("retention", "Retention", Archive, true)] : []),
    ...(can("manage_lab") ? [page("admin", "Lab details", Building2, true)] : []),
    help,
    settings,
  ];
}
