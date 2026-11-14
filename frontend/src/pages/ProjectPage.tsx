import { useMemo, useState, type ComponentType } from "react";
import { TabNav } from "@/components/shared/TabNav";
import {
  Navigate,
  Outlet,
  useLocation,
  useNavigate,
  useOutletContext,
  useParams,
  useSearchParams,
} from "react-router";
import { MessagesSquare, MoreHorizontal, Pencil } from "lucide-react";
import { toast } from "sonner";
import { DetailPanel } from "@/components/shared/DetailPanel";
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { UnreadBadge } from "@/components/layout/UnreadBadge";
import { useUnreadChats } from "@/hooks/chat";
import { useCreateDocument } from "@/hooks/documents";
import { useProjectCommands } from "@/hooks/researchCommands";
import { saveJson, useExportProject } from "@/hooks/research";
import { useDeleteProject, useProject, useUpdateProject } from "@/hooks/projects";
import type { Project } from "@/lib/api-types";
import { useRegisterCommands } from "@/lib/commands";
import { formErrors } from "@/lib/forms";
import { PROJECT_SECTIONS } from "@/lib/nav";
import { projectColorStyle } from "@/lib/projectColors";
import ChatTab from "@/pages/project/ChatTab";
import { ProjectDropZone } from "@/pages/project/ProjectDropZone";
import { ProjectFormDialog } from "@/pages/project/ProjectFormDialog";

/** Props every project tab component receives. */
export interface ProjectTabProps {
  labId: string;
  projectId: string;
  project: Project;
}

/** `/files` from before Files joined Documents, keeping any `?folder=`. */
export function FilesRedirect() {
  const { search } = useLocation();
  return <Navigate to={`../documents${search}`} relative="path" replace />;
}

/** Route element that hands the loaded project to a tab: `<ProjectTab as={MyTab} />`. */
export function ProjectTab({ as: Tab }: { as: ComponentType<ProjectTabProps> }) {
  return <Tab {...useOutletContext<ProjectTabProps>()} />;
}

export function ProjectPage() {
  const { labId = "", projectId = "" } = useParams();
  const navigate = useNavigate();
  const { data: project, error } = useProject(labId, projectId);
  const update = useUpdateProject(labId, projectId);
  const del = useDeleteProject(labId, projectId);
  const createDoc = useCreateDocument(labId, projectId);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  // In the address, so a link can open the panel and Back closes it.
  const [params, setParams] = useSearchParams();
  const chatOpen = params.get("chat") === "1";
  const setChatOpen = (open: boolean) =>
    setParams((p) => {
      if (open) p.set("chat", "1");
      else p.delete("chat");
      return p;
    });

  const unread = useUnreadChats(labId)[projectId] ?? 0;
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
      <div style={projectColorStyle(project.color)} className="border-l-4 border-(--project) pl-4">
        <PageHeader
          title={project.name}
          description={undefined}
          actions={
            <>
              <StatusBadge status={project.status} />
              <Button
                variant="ghost"
                aria-label={unread > 0 ? `Chat, ${unread} unread` : undefined}
                onClick={() => setChatOpen(true)}
              >
                <MessagesSquare aria-hidden /> Chat
                <UnreadBadge count={unread} noun="message" decorative />
              </Button>
              {can("edit_project") && (
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Edit"
                  title="Edit project"
                  onClick={() => setEditing(true)}
                >
                  <Pencil aria-hidden />
                </Button>
              )}
              {(can("export") || can("delete_project")) && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" aria-label="More project actions">
                      <MoreHorizontal aria-hidden />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {can("export") && (
                      <DropdownMenuItem
                        disabled={exportProject.isPending}
                        onSelect={() =>
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
                      </DropdownMenuItem>
                    )}
                    {can("export") && can("delete_project") && <DropdownMenuSeparator />}
                    {can("delete_project") && (
                      <DropdownMenuItem
                        className="text-destructive focus:text-destructive"
                        onSelect={() => setDeleting(true)}
                      >
                        Delete
                      </DropdownMenuItem>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </>
          }
        />
      </div>
      {/* The sidebar dropdown holds these from md up; below that the sidebar is a drawer. */}
      <TabNav
        label="Project sections"
        tabs={PROJECT_SECTIONS.map(({ to, label }) => [to, label])}
        className="mb-6 md:hidden"
      />
      <ProjectDropZone
        labId={labId}
        projectId={projectId}
        enabled={!!canEditContent}
        name={project.name}
      >
        <Outlet context={{ labId, projectId, project } satisfies ProjectTabProps} />
      </ProjectDropZone>
      <DetailPanel open={chatOpen} onOpenChange={setChatOpen} title="Project chat">
        <ChatTab labId={labId} projectId={projectId} project={project} />
      </DetailPanel>
      {editing && (
        <ProjectFormDialog
          open
          project={project}
          canRetention={project.my_permissions.includes("view_retention")}
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
