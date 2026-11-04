import { Home, ShieldCheck, Users } from "lucide-react";

/** Sidebar and palette links. Lab pages only appear once a lab is selected. */
export function navItems(labId?: string) {
  return [
    { to: "/", label: "Home", icon: Home, end: true },
    ...(labId ? [{ to: `/labs/${labId}/members`, label: "Members", icon: Users, end: false }] : []),
    { to: "/account", label: "Account", icon: ShieldCheck, end: false },
  ];
}
