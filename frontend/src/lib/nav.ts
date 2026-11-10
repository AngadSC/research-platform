import {
  Archive,
  Bell,
  BookOpen,
  Boxes,
  CalendarDays,
  CheckSquare,
  FileText,
  GraduationCap,
  History,
  LayoutDashboard,
  Home,
  MessagesSquare,
  Plug,
  Presentation,
  Settings,
  ShieldCheck,
  Users,
  Workflow,
} from "lucide-react";

/** The sections of a project: a dropdown in the sidebar, and tabs below md. */
export const PROJECT_SECTIONS = [
  { to: "overview", label: "Overview", icon: LayoutDashboard },
  { to: "tasks", label: "Tasks", icon: CheckSquare },
  { to: "documents", label: "Documents and files", icon: FileText },
  { to: "workflow", label: "Workflow", icon: Workflow },
  { to: "external", label: "External", icon: Presentation },
] as const;

/** Sidebar and palette links. Lab pages only appear once a lab is selected. */
export function navItems(labId?: string, permissions: string[] = [], inventoryEnabled = true) {
  return [
    { to: labId ? `/labs/${labId}/projects` : "/", label: "Home", icon: Home, end: true },
    ...(labId && permissions.includes("manage_lab")
      ? [{ to: `/labs/${labId}/dashboard`, label: "Dashboard", icon: LayoutDashboard, end: false }]
      : []),
    ...(labId
      ? [{ to: `/labs/${labId}/chat`, label: "Lab chat", icon: MessagesSquare, end: false }]
      : []),
    ...(labId
      ? [{ to: `/labs/${labId}/calendar`, label: "Calendar", icon: CalendarDays, end: false }]
      : []),
    ...(labId ? [{ to: `/labs/${labId}/members`, label: "Members", icon: Users, end: false }] : []),
    ...(labId && inventoryEnabled
      ? [{ to: `/labs/${labId}/inventory`, label: "Inventory", icon: Boxes, end: false }]
      : []),
    ...(labId
      ? [{ to: `/labs/${labId}/papers`, label: "Papers", icon: BookOpen, end: false }]
      : []),
    ...(labId
      ? [{ to: `/labs/${labId}/training`, label: "My training", icon: GraduationCap, end: false }]
      : []),
    ...(labId && permissions.includes("manage_lab")
      ? [{ to: `/labs/${labId}/admin`, label: "Admin", icon: ShieldCheck, end: false }]
      : []),
    ...(labId
      ? [{ to: `/labs/${labId}/notifications`, label: "Notifications", icon: Bell, end: false }]
      : []),
    ...(labId && permissions.includes("view_retention")
      ? [{ to: `/labs/${labId}/retention`, label: "Retention review", icon: Archive, end: false }]
      : []),
    ...(labId && permissions.includes("view_audit_log")
      ? [{ to: `/labs/${labId}/audit-log`, label: "Audit log", icon: History, end: false }]
      : []),
    ...(labId
      ? [
          {
            to: `/labs/${labId}/settings/integrations`,
            label: "Integrations",
            icon: Plug,
            end: false,
          },
        ]
      : []),
    { to: "/settings", label: "Settings", icon: Settings, end: false },
  ];
}
