import { FolderKanban, Plus } from "lucide-react";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { FormError } from "@/components/shared/FormError";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCreateProject, useProjects } from "@/hooks/projects";
import { ProjectFormDialog } from "@/pages/project/ProjectFormDialog";
import type { Project } from "@/lib/api-types";
import { useLab } from "@/hooks/workspace";
import { formErrors } from "@/lib/forms";

/** Active projects first (newest activity on top), archived ones last. */
export function activeFirst(list: Project[]): Project[] {
  const when = (p: Project) => p.last_activity_at ?? p.updated_at;
  return [...list].sort(
    (a, b) =>
      Number(a.status === "archived") - Number(b.status === "archived") ||
      when(b).localeCompare(when(a)),
  );
}

export function LabHomePage() {
  const { labId = "" } = useParams();
  const navigate = useNavigate();
  const { data: lab, error } = useLab(labId);
  const projects = useProjects(labId);
  const createProject = useCreateProject(labId);
  const [params, setParams] = useSearchParams();
  const creating = params.get("new") === "project";
  const canCreate = lab?.my_permissions.includes("create_project") ?? false;
  const setCreating = (open: boolean) =>
    setParams(open ? { new: "project" } : {}, { replace: true });

  const cols: Column<Project>[] = [
    { key: "name", header: "Project", cell: (p) => <span className="font-medium">{p.name}</span> },
    { key: "status", header: "Status", cell: (p) => <StatusBadge status={p.status} /> },
    {
      key: "updated",
      header: "Last edited",
      cell: (p) => <RelativeTime value={p.last_activity_at ?? p.updated_at} />,
    },
  ];

  if (error) return <FormError message={formErrors(error, []).form} />;
  if (!lab)
    return (
      <div aria-busy="true" aria-label="Loading" className="grid gap-3">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-48" />
      </div>
    );

  return (
    <>
      <PageHeader
        title="Projects"
        description={lab.name}
        actions={
          canCreate && (
            <Button onClick={() => setCreating(true)}>
              <Plus aria-hidden /> New project
            </Button>
          )
        }
      />
      <DataTable
        columns={cols}
        rows={activeFirst(projects.data ?? [])}
        getRowKey={(p) => p.id}
        loading={projects.isLoading}
        onRowClick={(p) => void navigate(`/labs/${labId}/projects/${p.id}`)}
        empty={
          <EmptyState
            icon={FolderKanban}
            title="No projects yet"
            description="Projects hold your tasks, documents and files for one piece of research."
            action={
              canCreate ? <Button onClick={() => setCreating(true)}>New project</Button> : undefined
            }
          />
        }
      />
      {creating && canCreate && (
        <ProjectFormDialog
          open
          canRetention={lab.my_permissions.includes("view_retention")}
          onOpenChange={setCreating}
          onSave={async (v) => {
            const p = await createProject.mutateAsync(v);
            void navigate(`/labs/${labId}/projects/${p.id}`);
          }}
        />
      )}
    </>
  );
}
