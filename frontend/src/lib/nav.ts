import { Archive, Bell, FileCheck2, History, Home, Plug, ShieldCheck, Users } from "lucide-react";

/** Sidebar and palette links. Lab pages only appear once a lab is selected. */
export function navItems(labId?: string, permissions: string[] = []) {
  return [
    { to: "/", label: "Home", icon: Home, end: true },
    ...(labId ? [{ to: `/labs/${labId}/members`, label: "Members", icon: Users, end: false }] : []),
    ...(labId && permissions.includes("view_ethics")
      ? [{ to: `/labs/${labId}/ethics`, label: "Ethics approvals", icon: FileCheck2, end: false }]
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
    { to: "/account", label: "Account", icon: ShieldCheck, end: false },
  ];
}
