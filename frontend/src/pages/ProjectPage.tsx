import { useMemo, useState, type ComponentType } from "react";
import { NavLink, Outlet, useNavigate, useOutletContext, useParams } from "react-router";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useCreateDocument } from "@/hooks/documents";
import { useProjectCommands } from "@/hooks/researchCommands";
import { saveJson, useExportProject } from "@/hooks/research";
import { useDeleteProject, useProject, useUpdateProject } from "@/hooks/projects";
import type { Project } from "@/lib/api-types";
import { useRegisterCommands } from "@/lib/commands";
import { cn } from "@/lib/utils";
import { formErrors } from "@/lib/forms";
import { ProjectFormDialog } from "@/pages/project/ProjectFormDialog";

/** Props every project tab component receives. */
export interface ProjectTabProps {
  labId: string;
  projectId: string;
  project: Project;
}

/** Route element that hands the loaded project to a tab: `<ProjectTab as={MyTab} />`. */
export function ProjectTab({ as: Tab }: { as: ComponentType<ProjectTabProps> }) {
  return <Tab {...useOutletContext<ProjectTabProps>()} />;
}

const TABS = [
  ["overview", "Overview"],
  ["tasks", "Tasks"],
  ["documents", "Documents"],
  ["files", "Files"],
  ["research", "Research"],
  ["lineage", "Lineage"],
] as const;

export function ProjectPage() {
  const { labId = "", projectId = "" } = useParams();
  const navigate = useNavigate();
  const { data: project, error } = useProject(labId, projectId);
  const update = useUpdateProject(labId, projectId);
  const del = useDeleteProject(labId, projectId);
  const createDoc = useCreateDocument(labId, projectId);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const canEditContent = project?.my_permissions.includes("edit_content");
  const exportProject = useExportProject(labId, projectId);
  useProjectCommands(labId, projectId, !!canEditContent);
  useRegisterCommands(
    useMemo(
      () =>
        canEditContent
          ? [
              {
                id: "task:new",
                label: "New task",
                group: "Actions",
                onSelect: () =>
                  void navigate(`/labs/${labId}/projects/${projectId}/tasks?new=task`),
              },
              {
                id: "document:new",
                label: "New document",
                group: "Actions",
                onSelect: () =>
                  createDoc.mutate("Untitled document", {
                    onSuccess: (d) =>
                      void navigate(`/labs/${labId}/projects/${projectId}/documents/${d.id}`),
                    onError: () => toast.error("Could not create the document. Please try again."),
                  }),
              },
            ]
          : [],
      // eslint-disable-next-line react-hooks/exhaustive-deps -- mutate is stable
      [canEditContent, navigate, labId, projectId, createDoc.mutate],
    ),
  );

  if (error) return <FormError message={formErrors(error, []).form} />;
  if (!project)
    return (
      <div aria-busy="true" aria-label="Loading" className="grid gap-3">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-48" />
      </div>
    );
  const can = (perm: string) => project.my_permissions.includes(perm);

  return (
    <>
      <PageHeader
        title={project.name}
        description={undefined}
        actions={
          <>
            <StatusBadge status={project.status} />
            {can("export") && (
              <Button
                variant="outline"
                disabled={exportProject.isPending}
                onClick={() =>
                  exportProject.mutate(undefined, {
                    onSuccess: (d) => {
                      saveJson(d, `${project.name.replace(/[^\w-]+/g, "-")}-export.json`);
                      toast.success("Project exported");
                    },
                    onError: (e) => toast.error(formErrors(e, []).form ?? "Export failed."),
                  })
                }
              >
                Export project
              </Button>
            )}
            {can("edit_project") && (
              <Button variant="outline" onClick={() => setEditing(true)}>
                Edit
              </Button>
            )}
            {can("delete_project") && (
              <Button variant="outline" onClick={() => setDeleting(true)}>
                Delete
              </Button>
            )}
          </>
        }
      />
      <nav aria-label="Project sections" className="mb-6 flex gap-1 border-b">
        {TABS.map(([to, label]) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "-mb-px border-b-2 px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                isActive
                  ? "border-primary font-medium"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>
      <Outlet context={{ labId, projectId, project } satisfies ProjectTabProps} />
      {editing && (
        <ProjectFormDialog
          open
          project={project}
          onOpenChange={setEditing}
          onSave={(v) => update.mutateAsync(v)}
        />
      )}
      <Dialog open={deleting} onOpenChange={setDeleting}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">Delete {project.name}?</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            This is a soft delete: the project is hidden from everyone, but its data is kept and not
            permanently erased.
          </DialogDescription>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button
              variant="destructive"
              disabled={del.isPending}
              onClick={() =>
                del.mutate(undefined, {
                  onSuccess: () => {
                    toast.success("Project deleted");
                    void navigate(`/labs/${labId}`);
                  },
                  onError: (e) => toast.error(formErrors(e, []).form ?? "Something went wrong."),
                  onSettled: () => setDeleting(false),
                })
              }
            >
              Delete project
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
