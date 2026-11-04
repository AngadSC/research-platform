import { useMemo } from "react";
import { Outlet, useNavigate } from "react-router";
import { Breadcrumbs } from "@/components/shared/Breadcrumbs";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { useCrumbs, useCurrentLabId } from "@/hooks/crumbs";
import { useProjects } from "@/hooks/projects";
import { useLabs } from "@/hooks/workspace";
import { useRegisterCommands, type Command } from "@/lib/commands";
import { CommandPalette } from "./CommandPalette";
import { navItems } from "@/lib/nav";
import { Sidebar } from "./Sidebar";

export function AppShell() {
  const navigate = useNavigate();
  const crumbs = useCrumbs();
  const labId = useCurrentLabId();
  const { data: labs } = useLabs();
  const { data: projects } = useProjects(labId);

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
      <div className="flex h-screen bg-background text-foreground">
        <Sidebar />
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-5xl px-8 py-6">
            <div className="mb-4">
              <Breadcrumbs items={crumbs} />
            </div>
            <Outlet />
          </div>
        </main>
      </div>
      <CommandPalette />
      <Toaster />
    </TooltipProvider>
  );
}
