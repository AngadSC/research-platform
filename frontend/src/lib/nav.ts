import { History, Home, ShieldCheck, Users } from "lucide-react";

/** Sidebar and palette links. Lab pages only appear once a lab is selected. */
export function navItems(labId?: string, permissions: string[] = []) {
  return [
    { to: "/", label: "Home", icon: Home, end: true },
    ...(labId ? [{ to: `/labs/${labId}/members`, label: "Members", icon: Users, end: false }] : []),
    ...(labId && permissions.includes("view_audit_log")
      ? [{ to: `/labs/${labId}/audit-log`, label: "Audit log", icon: History, end: false }]
      : []),
    { to: "/account", label: "Account", icon: ShieldCheck, end: false },
  ];
}
