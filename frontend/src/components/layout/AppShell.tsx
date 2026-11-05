import { useEffect, useMemo, useState } from "react";
import { Menu } from "lucide-react";
import { Outlet, useNavigate } from "react-router";
import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/sonner";
import { useCrumbs, useCurrentLabId } from "@/hooks/crumbs";
import { useProjects } from "@/hooks/projects";
import { useLabs } from "@/hooks/workspace";
import { useRegisterCommands, type Command } from "@/lib/commands";
import { CommandPalette } from "./CommandPalette";
import { navItems } from "@/lib/nav";
import { APP_NAME } from "@/lib/constants";
import { Sidebar } from "./Sidebar";

export function AppShell() {
  const navigate = useNavigate();
  const crumbs = useCrumbs();
  const labId = useCurrentLabId();
  const { data: labs } = useLabs();
  const { data: projects } = useProjects(labId);
  const [navOpen, setNavOpen] = useState(false);

  // Below md the sidebar is a drawer: Escape closes it.
  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setNavOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [navOpen]);

  const commands = useMemo<Command[]>(
    () => [
      ...navItems(labId, labs?.find((l) => l.id === labId)?.my_permissions).map((n) => ({
        id: `nav:${n.to}`,
        label: `Go to ${n.label}`,
        group: "Navigate",
        icon: n.icon,
        onSelect: () => void navigate(n.to),
      })),
      ...(projects ?? []).map((p) => ({
        id: `project:${p.id}`,
        label: `Go to project ${p.name}`,
        group: "Projects",
        onSelect: () => void navigate(`/labs/${labId}/projects/${p.id}`),
      })),
      ...(labs ?? []).map((l) => ({
        id: `lab:${l.id}`,
        label: `Switch to ${l.name}`,
        group: "Labs",
        onSelect: () => void navigate(`/labs/${l.id}`),
      })),
      {
        id: "lab:new",
        label: "Create a lab",
        group: "Labs",
        onSelect: () => void navigate("/labs/new"),
      },
    ],
    [navigate, labId, labs, projects],
  );
  useRegisterCommands(commands);

  return (
    <TooltipProvider>
      <div className="flex h-screen bg-background text-foreground print:block print:h-auto">
        <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />
        {navOpen && (
          <div
            aria-hidden
            className="fixed inset-0 z-40 bg-black/40 md:hidden"
            onClick={() => setNavOpen(false)}
          />
        )}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center gap-2 border-b px-3 py-2 print:hidden md:hidden">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Open navigation"
              aria-controls="app-sidebar"
              aria-expanded={navOpen}
              onClick={() => setNavOpen(true)}
            >
              <Menu aria-hidden />
            </Button>
            <span className="text-sm font-semibold">{APP_NAME}</span>
          </header>
          <main className="min-h-0 flex-1 overflow-y-auto print:overflow-visible">
            <div className="mx-auto max-w-5xl px-4 py-6 md:px-8 print:max-w-none print:px-0">
              <div className="mb-4 print:hidden">
                <Breadcrumbs items={crumbs} />
              </div>
              <Outlet />
            </div>
          </main>
        </div>
      </div>
      <CommandPalette labId={labId} onGo={(url) => void navigate(url)} />
      <Toaster />
    </TooltipProvider>
  );
}
