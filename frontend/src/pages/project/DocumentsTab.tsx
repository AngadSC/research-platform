import {
  Download,
  Eye,
  FileText,
  FolderInput,
  Link2,
  MoreHorizontal,
  Plus,
  Trash2,
  Upload,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { Link, useNavigate } from "react-router";
import { toast } from "sonner";
import { FolderBrowser, MoveDialog, type Movable } from "@/components/documents/Folders";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { LinkedFiles } from "@/components/shared/LinkedFiles";
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
import { downloadUrl, useAttachments } from "@/hooks/projects";
import { personName, type Attachment, type DocumentRow } from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { UploadDialog } from "@/pages/project/UploadDialog";

const isPdf = (a: Attachment) =>
  a.content_type === "application/pdf" || a.original_filename.toLowerCase().endsWith(".pdf");
const size = (n: number) =>
  n < 1024
    ? `${n} B`
    : n < 1048576
      ? `${(n / 1024).toFixed(1)} KB`
      : `${(n / 1048576).toFixed(1)} MB`;

type Row = { doc: DocumentRow; file?: never } | { file: Attachment; doc?: never };
const rowId = (r: Row) => (r.doc ? r.doc.id : r.file.id);
const rowName = (r: Row) => (r.doc ? r.doc.title : r.file.original_filename);
const rowDate = (r: Row) => (r.doc ? r.doc.updated_at : r.file.created_at);
const rowFolder = (r: Row) => (r.doc ? r.doc.folder : r.file.folder) ?? null;

/** Documents and uploaded files together, in one folder tree. Every server check is unchanged. */
export default function DocumentsTab({ labId, projectId, project }: ProjectTabProps) {
  const navigate = useNavigate();
  const docs = useDocuments(labId, projectId);
  const create = useCreateDocument(labId, projectId);
  const removeDoc = useDeleteDocument(labId, projectId);
  const { list: files, uploadFile, remove: removeFile } = useAttachments(labId, projectId);
  const canEdit = project.my_permissions.includes("edit_content");
  const folder = useCurrentFolder();
  const [deleting, setDeleting] = useState<Row | null>(null);
  const [moving, setMoving] = useState<Movable | null>(null);
  const [embedding, setEmbedding] = useState(false);
  const [uploading, setUploading] = useState(false);
  const base = `/labs/${labId}/projects/${projectId}`;
  const open = (id: string) => void navigate(`${base}/documents/${id}`);
  const add = () =>
    create.mutate(
      { title: "Untitled document", folder },
      {
        onSuccess: (d) => open(d.id),
        onError: (e) => toast.error(formErrors(e, []).form ?? "Something went wrong."),
      },
    );
  const rows: Row[] = [
    ...(docs.data ?? []).map((doc) => ({ doc })),
    ...(files.data ?? []).map((file) => ({ file })),
  ]
    .filter((r) => rowFolder(r) === folder)
    .sort((a, b) => rowDate(b).localeCompare(rowDate(a)));

  const startMove = (r: Row) =>
    setMoving({
      kind: r.doc ? "documents" : "attachments",
      id: rowId(r),
      name: rowName(r),
      folder: rowFolder(r),
    });
  const confirmDelete = () => {
    if (!deleting) return;
    const done = {
      onSuccess: () => toast.success(deleting.doc ? "Document deleted" : "File deleted"),
      onError: (e: unknown) => toast.error(formErrors(e, []).form ?? "Something went wrong."),
      onSettled: () => setDeleting(null),
    };
    if (deleting.doc) removeDoc.mutate(deleting.doc.id, done);
    else removeFile.mutate(deleting.file.id, done);
  };

  const cols: Column<Row>[] = [
    {
      key: "name",
      header: "Name",
      cell: (r) => <span className="font-medium">{rowName(r)}</span>,
    },
    {
      key: "type",
      header: "Type",
      cell: (r) =>
        r.doc
          ? "Document"
          : `${isPdf(r.file) ? "PDF" : r.file.content_type || "File"}, ${size(r.file.size_bytes)}`,
    },
    {
      key: "by",
      header: "Last changed by",
      cell: (r) => personName(r.doc ? r.doc.updated_by : r.file.uploaded_by),
    },
    { key: "at", header: "Updated", cell: (r) => <RelativeTime value={rowDate(r)} /> },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (r) => (
        // A row click opens a document, so the buttons here must not reach it.
        <div
          className="flex justify-end gap-1"
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
        >
          {r.file && isPdf(r.file) && (
            <Button variant="ghost" size="sm" asChild>
              <Link to={`${base}/files/${r.file.id}`} aria-label={`Open ${rowName(r)}`}>
                <Eye aria-hidden />
              </Link>
            </Button>
          )}
          {r.file && (
            <Button variant="ghost" size="sm" asChild>
              <a
                href={downloadUrl(labId, r.file.id)}
                download
                aria-label={`Download ${rowName(r)}`}
              >
                <Download aria-hidden />
              </a>
            </Button>
          )}
          {canEdit && r.file && (
            <>
              <Button
                variant="ghost"
                size="sm"
                aria-label={`Move ${rowName(r)}`}
                onClick={() => startMove(r)}
              >
                <FolderInput aria-hidden />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                aria-label={`Delete ${rowName(r)}`}
                onClick={() => setDeleting(r)}
              >
                <Trash2 aria-hidden />
              </Button>
            </>
          )}
          {canEdit && r.doc && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" aria-label={`Actions for ${rowName(r)}`}>
                  <MoreHorizontal aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => startMove(r)}>Move to folder</DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setDeleting(r)}>Delete</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      ),
    },
  ];

  const noun = deleting?.doc ? "document" : "file";
  return (
    <div className="grid gap-4">
      {canEdit && (
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="outline" onClick={() => setEmbedding(true)}>
            <Link2 className="size-4" /> Embed a document
          </Button>
          <Button variant="outline" onClick={() => setUploading(true)}>
            <Upload aria-hidden /> Upload file
          </Button>
          <Button disabled={create.isPending} onClick={add}>
            <Plus className="size-4" /> New document
          </Button>
        </div>
      )}
      <FolderBrowser labId={labId} projectId={projectId} canEdit={canEdit} />
      <DataTable
        loading={docs.isLoading || files.isLoading}
        rows={rows}
        columns={cols}
        getRowKey={rowId}
        onRowClick={(r) => {
          if (r.doc) open(r.doc.id);
          else if (isPdf(r.file)) void navigate(`${base}/files/${r.file.id}`);
          else window.location.assign(downloadUrl(labId, r.file.id));
        }}
        empty={
          <EmptyState
            icon={FileText}
            title={folder ? "Nothing in this folder" : "No documents or files yet"}
            description="Notes, protocols and write-ups for this project live here, with anonymized or aggregate data and papers. PDFs open right here."
          />
        }
      />
      <MoveDialog
        labId={labId}
        projectId={projectId}
        item={moving}
        onClose={() => setMoving(null)}
      />
      <section aria-labelledby="linked-files" className="grid gap-2">
        <h2 id="linked-files" className="text-sm font-medium">
          Linked files
        </h2>
        <LinkedFiles labId={labId} projectId={projectId} canEdit={canEdit} />
      </section>
      <UploadDialog
        open={uploading}
        onOpenChange={setUploading}
        send={(file, onProgress) => uploadFile.mutateAsync({ file, onProgress, folder })}
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
          <DialogTitle className="text-base font-semibold">
            Delete {deleting && rowName(deleting)}?
          </DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            The {noun} will be removed from this project.
          </DialogDescription>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button
              variant="destructive"
              disabled={removeDoc.isPending || removeFile.isPending}
              onClick={confirmDelete}
            >
              Delete {noun}
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
