import { FileText, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { PageHeader } from "@/components/shared/PageHeader";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useCreateDocument, useDocuments } from "@/hooks/documents";
import { useLab } from "@/hooks/workspace";
import { personName, type DocumentRow } from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";

const COLUMNS: Column<DocumentRow>[] = [
  { key: "title", header: "Title", cell: (d) => <span className="font-medium">{d.title}</span> },
  { key: "editor", header: "Last edited by", cell: (d) => personName(d.updated_by) },
  { key: "updated", header: "Updated", cell: (d) => <RelativeTime value={d.updated_at} /> },
];

/** D233: documents that belong to the whole lab rather than to one project. */
export function LabDocumentsPage() {
  const { labId = "" } = useParams();
  const navigate = useNavigate();
  const { data: lab } = useLab(labId);
  const docs = useDocuments(labId, "");
  const create = useCreateDocument(labId, "");
  const [adding, setAdding] = useState(false);
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const canAdd = lab?.my_permissions.includes("contribute_lab") ?? false;
  const open = (id: string) => void navigate(`/labs/${labId}/documents/${id}`);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const title = String(f.get("title") ?? "").trim();
    if (!title) return setErrors({ fields: { title: "Enter a title" } });
    const embedUrl = String(f.get("embed_url") ?? "").trim();
    setErrors({ fields: {} });
    try {
      const doc = await create.mutateAsync({
        title,
        ...(embedUrl && { embed_url: embedUrl }),
      });
      open(doc.id);
    } catch (err) {
      setErrors(formErrors(err, ["title", "embed_url"]));
    }
  }

  const addButton = canAdd ? (
    <Button onClick={() => setAdding(true)}>
      <Plus aria-hidden />
      New document
    </Button>
  ) : undefined;

  return (
    <>
      <PageHeader
        title="Lab documents"
        description="The lab manual, protocols and SOPs. Everyone in the lab can read these."
        actions={addButton}
      />
      <DataTable
        columns={COLUMNS}
        rows={docs.data ?? []}
        getRowKey={(d) => d.id}
        loading={docs.isLoading}
        onRowClick={(d) => open(d.id)}
        empty={
          <EmptyState
            icon={FileText}
            title="No lab documents yet"
            description={
              canAdd
                ? "Write something the whole lab needs, such as a lab manual or an SOP."
                : "Only lab members who can edit can add documents. Ask a PI or lab admin."
            }
            action={addButton}
          />
        }
      />
      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">New lab document</DialogTitle>
          <DialogDescription className="sr-only">Name the document.</DialogDescription>
          <form onSubmit={submit} noValidate className="grid gap-4">
            <FormField label="Title" error={errors.fields.title}>
              {(p) => <Input maxLength={300} {...p} name="title" autoComplete="off" />}
            </FormField>
            <FormField
              label="Link to a Google or Microsoft file (optional)"
              error={errors.fields.embed_url}
            >
              {(p) => (
                <Input maxLength={2000} {...p} name="embed_url" type="url" autoComplete="off" />
              )}
            </FormField>
            <FormError message={errors.form} />
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setAdding(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={create.isPending}>
                Create
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
