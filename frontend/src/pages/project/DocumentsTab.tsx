import { FileText, Plus } from "lucide-react";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { DataTable } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { useCreateDocument, useDocuments } from "@/hooks/documents";
import { personName } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";
import type { ProjectTabProps } from "@/pages/ProjectPage";

export default function DocumentsTab({ labId, projectId, project }: ProjectTabProps) {
  const navigate = useNavigate();
  const { data, isLoading } = useDocuments(labId, projectId);
  const create = useCreateDocument(labId, projectId);
  const canEdit = project.my_permissions.includes("edit_content");
  const open = (id: string) =>
    void navigate(`/labs/${labId}/projects/${projectId}/documents/${id}`);
  const add = () =>
    create.mutate("Untitled document", {
      onSuccess: (d) => open(d.id),
      onError: (e) => toast.error(formErrors(e, []).form ?? "Something went wrong."),
    });
  const newButton = (
    <Button disabled={create.isPending} onClick={add}>
      <Plus className="size-4" /> New document
    </Button>
  );

  return (
    <div className="flex flex-col gap-4">
      {!!data?.length && canEdit && <div className="flex justify-end">{newButton}</div>}
      <DataTable
        loading={isLoading}
        rows={data ?? []}
        getRowKey={(d) => d.id}
        onRowClick={(d) => open(d.id)}
        columns={[
          {
            key: "title",
            header: "Title",
            cell: (d) => <span className="font-medium">{d.title}</span>,
          },
          { key: "by", header: "Last edited by", cell: (d) => personName(d.updated_by) },
          { key: "at", header: "Updated", cell: (d) => <RelativeTime value={d.updated_at} /> },
        ]}
        empty={
          <EmptyState
            icon={FileText}
            title="No documents yet"
            description="Notes, protocols and write-ups for this project live here."
            action={canEdit ? newButton : undefined}
          />
        }
      />
    </div>
  );
}
