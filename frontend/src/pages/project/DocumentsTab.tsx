import { FileText, Link2, MoreHorizontal, Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { FolderBrowser, MoveDialog, type Movable } from "@/components/documents/Folders";
import { DataTable } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
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
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  useCreateDocument,
  useCurrentFolder,
  useDeleteDocument,
  useDocuments,
} from "@/hooks/documents";
import { personName, type DocumentRow } from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import type { ProjectTabProps } from "@/pages/ProjectPage";

export default function DocumentsTab({ labId, projectId, project }: ProjectTabProps) {
  const navigate = useNavigate();
  const { data, isLoading } = useDocuments(labId, projectId);
  const create = useCreateDocument(labId, projectId);
  const remove = useDeleteDocument(labId, projectId);
  const canEdit = project.my_permissions.includes("edit_content");
  const folder = useCurrentFolder();
  const [deleting, setDeleting] = useState<DocumentRow | null>(null);
  const [moving, setMoving] = useState<Movable | null>(null);
  const [embedding, setEmbedding] = useState(false);
  const open = (id: string) =>
    void navigate(`/labs/${labId}/projects/${projectId}/documents/${id}`);
  const add = () =>
    create.mutate(
      { title: "Untitled document", folder },
      {
        onSuccess: (d) => open(d.id),
        onError: (e) => toast.error(formErrors(e, []).form ?? "Something went wrong."),
      },
    );
  const rows = (data ?? []).filter((d) => (d.folder ?? null) === folder);
  const newButton = (
    <Button disabled={create.isPending} onClick={add}>
      <Plus className="size-4" /> New document
    </Button>
  );

  return (
    <div className="flex flex-col gap-4">
      {canEdit && (
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => setEmbedding(true)}>
            <Link2 className="size-4" /> Embed a document
          </Button>
          {newButton}
        </div>
      )}
      <FolderBrowser labId={labId} projectId={projectId} canEdit={canEdit} />
      <DataTable
        loading={isLoading}
        rows={rows}
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
          ...(canEdit
            ? [
                {
                  key: "actions",
                  header: "",
                  className: "text-right",
                  cell: (d: DocumentRow) => (
                    <div
                      onClick={(e) => e.stopPropagation()}
                      onKeyDown={(e) => e.stopPropagation()}
                    >
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="sm" aria-label={`Actions for ${d.title}`}>
                            <MoreHorizontal aria-hidden />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onSelect={() =>
                              setMoving({
                                kind: "documents",
                                id: d.id,
                                name: d.title,
                                folder: d.folder ?? null,
                              })
                            }
                          >
                            Move to folder
                          </DropdownMenuItem>
                          <DropdownMenuItem onSelect={() => setDeleting(d)}>
                            Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  ),
                },
              ]
            : []),
        ]}
        empty={
          <EmptyState
            icon={FileText}
            title={folder ? "No documents in this folder" : "No documents yet"}
            description="Notes, protocols and write-ups for this project live here."
          />
        }
      />
      <MoveDialog
        labId={labId}
        projectId={projectId}
        item={moving}
        onClose={() => setMoving(null)}
      />
      <EmbedDialog
        open={embedding}
        onOpenChange={setEmbedding}
        submitting={create.isPending}
        onSubmit={(title, url, onError) =>
          create.mutate(
            { title, embed_url: url, folder },
            { onSuccess: (d) => open(d.id), onError },
          )
        }
      />
      <Dialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">Delete {deleting?.title}?</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            The document will be removed from this project.
          </DialogDescription>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() =>
                deleting &&
                remove.mutate(deleting.id, {
                  onSuccess: () => toast.success("Document deleted"),
                  onError: (e) => toast.error(formErrors(e, []).form ?? "Something went wrong."),
                  onSettled: () => setDeleting(null),
                })
              }
            >
              Delete document
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function EmbedDialog({
  open,
  onOpenChange,
  submitting,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  submitting: boolean;
  onSubmit: (title: string, url: string, onError: (e: unknown) => void) => void;
}) {
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setErrors({ fields: {} });
    onSubmit(title.trim(), url.trim(), (err) => setErrors(formErrors(err, ["title", "embed_url"])));
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">Embed a document</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          Paste a share link from Google Docs, Sheets or Slides, or from OneDrive or SharePoint.
          People viewing it still need access to the file.
        </DialogDescription>
        <form onSubmit={submit} className="grid gap-3">
          <FormField label="Title" error={errors.fields.title}>
            {(p) => (
              <Input
                {...p}
                required
                maxLength={300}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            )}
          </FormField>
          <FormField label="Link" error={errors.fields.embed_url}>
            {(p) => (
              <Input
                {...p}
                required
                type="url"
                placeholder="https://docs.google.com/document/d/..."
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            )}
          </FormField>
          <FormError message={errors.form} />
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline" type="button">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={submitting}>
              Embed
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
