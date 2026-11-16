import {
  Bell,
  CloudSun,
  Pin,
  Plus,
  Search,
  Smile,
  Sparkles,
  Star,
  type LucideIcon,
} from "lucide-react";

/** One thing that can sit in the top bar. */
export interface TopbarItem {
  id: string;
  label: string;
  hint: string;
  icon: LucideIcon;
}

/** The top bar's own buttons. Page shortcuts (`nav-…`) are added from the sidebar's links. */
export const TOPBAR_BUILTIN: TopbarItem[] = [
  { id: "greeting", label: "Greeting", hint: "Your name and the day", icon: Smile },
  { id: "pin", label: "Pin this page", hint: "Adds the page you are on to your pins", icon: Pin },
  { id: "pins", label: "Pinned pages", hint: "Your pinned pages as shortcuts", icon: Star },
  { id: "search", label: "Search", hint: "Find anything, or run an action", icon: Search },
  { id: "task", label: "Add a task", hint: "Capture a task from anywhere", icon: Plus },
  { id: "assistant", label: "Assistant", hint: "Ask about your lab", icon: Sparkles },
  {
    id: "weather",
    label: "Weather and location",
    hint: "Temperature and place, once you allow your location",
    icon: CloudSun,
  },
  { id: "bell", label: "Notifications", hint: "What needs you", icon: Bell },
];

/** What a person sees until they change it. */
export const TOPBAR_DEFAULT = ["greeting", "pin", "search", "task", "assistant", "weather", "bell"];

/** The part of a lab link that names the page: `/labs/<id>/my-work` is "my-work". */
export const navKey = (to: string) => to.replace(/^\/labs\/[^/]+\//, "");

/** Top bar id for a page shortcut. Ids keep to letters, digits and hyphens. */
export const shortcutId = (to: string) => `nav-${navKey(to).replace(/\//g, "-")}`;
