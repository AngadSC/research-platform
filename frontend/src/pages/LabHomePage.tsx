import { FolderKanban, Plus } from "lucide-react";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { PageHeader } from "@/components/shared/PageHeader";
import { Recents } from "@/components/shared/Recents";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useCreateProject, useProjects } from "@/hooks/projects";
import { ProjectFormDialog } from "@/pages/project/ProjectFormDialog";
import type { Project } from "@/lib/api-types";
import { useLab, useUpdateLab } from "@/hooks/workspace";
import { formErrors, type FormErrors } from "@/lib/forms";
import { roleLabel } from "@/lib/api-types";

function RenameForm({ labId, name }: { labId: string; name: string }) {
  const update = useUpdateLab(labId);
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const next = String(new FormData(e.currentTarget).get("name") ?? "").trim();
    if (!next) return setErrors({ fields: { name: "Enter a name for your lab" } });
    setErrors({ fields: {} });
    try {
      await update.mutateAsync({ name: next });
      toast.success("Saved");
    } catch (err) {
      setErrors(formErrors(err, ["name"]));
    }
  }

  return (
    <form onSubmit={submit} noValidate className="mb-8 grid max-w-sm gap-4">
      <FormField label="Lab name" error={errors.fields.name}>
        {(p) => <Input {...p} name="name" defaultValue={name} autoComplete="off" />}
      </FormField>
      <FormError message={errors.form} />
      <Button type="submit" className="justify-self-start" disabled={update.isPending}>
        Save
      </Button>
    </form>
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
      header: "Updated",
      cell: (p) => <RelativeTime value={p.updated_at} />,
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
        title={lab.name}
        description={`${lab.institution.name} · You are ${roleLabel(lab.my_role ?? "")}`}
        actions={
          <>
            <Button asChild variant="outline">
              <Link to={`/labs/${lab.id}/members`}>Members</Link>
            </Button>
            {canCreate && (
              <Button onClick={() => setCreating(true)}>
                <Plus aria-hidden /> New project
              </Button>
            )}
          </>
        }
      />
      {lab.my_permissions.includes("manage_lab") && <RenameForm labId={lab.id} name={lab.name} />}
      <Recents />
      <section className="grid gap-3">
        <h2 className="text-base font-semibold">Projects</h2>
        <DataTable
          columns={cols}
          rows={projects.data ?? []}
          getRowKey={(p) => p.id}
          loading={projects.isLoading}
          onRowClick={(p) => void navigate(`/labs/${labId}/projects/${p.id}`)}
          empty={
            <EmptyState
              icon={FolderKanban}
              title="No projects yet"
              description="Projects hold your tasks, documents and files for one piece of research."
              action={
                canCreate ? (
                  <Button onClick={() => setCreating(true)}>New project</Button>
                ) : undefined
              }
            />
          }
        />
      </section>
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
