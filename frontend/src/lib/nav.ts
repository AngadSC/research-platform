import {
  Archive,
  Bell,
  Boxes,
  GraduationCap,
  History,
  LayoutDashboard,
  Home,
  Plug,
  Settings,
  ShieldCheck,
  Users,
} from "lucide-react";

/** Sidebar and palette links. Lab pages only appear once a lab is selected. */
export function navItems(labId?: string, permissions: string[] = []) {
  return [
    { to: "/", label: "Home", icon: Home, end: true },
    ...(labId && permissions.includes("manage_lab")
      ? [{ to: `/labs/${labId}/dashboard`, label: "Dashboard", icon: LayoutDashboard, end: false }]
      : []),
    ...(labId ? [{ to: `/labs/${labId}/members`, label: "Members", icon: Users, end: false }] : []),
    ...(labId
      ? [{ to: `/labs/${labId}/inventory`, label: "Inventory", icon: Boxes, end: false }]
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
