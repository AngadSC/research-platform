import {
  Archive,
  BarChart3,
  Bug,
  Bell,
  BookOpen,
  Boxes,
  Thermometer,
  Building2,
  CalendarDays,
  CheckSquare,
  CircleHelp,
  FileText,
  FolderKanban,
  GraduationCap,
  History,
  Landmark,
  LayoutDashboard,
  Home,
  ListChecks,
  MessagesSquare,
  NotebookPen,
  NotebookText,
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
  {
    to: "notebook",
    label: "Notebook",
    icon: NotebookText,
    hint: "The project's shared lab notebook",
  },
  { to: "documents", label: "Documents and files", icon: FileText },
  { to: "participants", label: "Participants", icon: Users },
  {
    to: "subjects",
    label: "Subjects",
    icon: Bug,
    hint: "Animals, strains, cell lines and samples",
  },
  {
    to: "workflow",
    label: "Workflow",
    icon: Workflow,
    hint: "Funding, ethics, participants, data, analysis, manuscript and review",
  },
  { to: "analyse", label: "Statistics", icon: BarChart3 },
  { to: "external", label: "Presentations", icon: Presentation },
] as const;

/** The kinds of study a project can have, with how to say them (D329). */
export const STUDY_TYPES = [
  { value: "human", label: "People", help: "Human participants, with coded IDs" },
  { value: "animal", label: "Animals", help: "Mice, rats, fish, flies and other cohorts" },
  { value: "microbial", label: "Microbes", help: "Bacterial, yeast or viral strains and cultures" },
  { value: "cell_line", label: "Cell lines", help: "Lines, passages and stocks" },
  { value: "samples", label: "Samples", help: "Tissue, blood, soil and other specimens" },
  { value: "computational", label: "Computational", help: "Code, models and existing data only" },
] as const;

/** The pages a project shows: Participants for studies of people, Subjects for anything else that
 * is studied (animals, microbes, cell lines, samples). A project that says nothing shows the
 * participants it always had. */
export function projectSections(studyTypes: readonly string[] | undefined) {
  const types = studyTypes ?? ["human"];
  const people = types.includes("human");
  const things = types.some((t) => ["animal", "microbial", "cell_line", "samples"].includes(t));
  return PROJECT_SECTIONS.filter(
    (s) => (s.to !== "participants" || people) && (s.to !== "subjects" || things),
  );
}

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
    page("notebook", "My notebook", NotebookPen),
    page("participants", "Participants", Users),
    page("members", "Members", Users),
    ...(inventoryEnabled
      ? [page("inventory", "Inventory", Boxes), page("monitoring", "Monitoring", Thermometer)]
      : []), // D227: wet labs only
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
    ...(can("access_funding") ? [page("funding", "Funding", Landmark, true)] : []), // PIs only (D226)
    ...(can("view_retention") ? [page("retention", "Retention", Archive, true)] : []),
    ...(can("manage_lab") ? [page("admin", "Lab details", Building2, true)] : []),
    help,
    settings,
  ];
}
