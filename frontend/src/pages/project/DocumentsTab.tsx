import {
  Download,
  Eye,
  FileText,
  FolderInput,
  Link2,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
  Upload,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { FilePreview } from "@/components/documents/FilePreview";
import { FolderBrowser, MoveDialog, type Movable } from "@/components/documents/Folders";
import { DataTable, HIDE_NARROW, HIDE_NARROWER, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { GoogleEditorPanel } from "@/components/shared/GoogleEditorPanel";
import { LinkedFiles } from "@/components/shared/LinkedFiles";
import { PARTICIPANT_HINT, ParticipantBadge } from "@/components/shared/ParticipantData";
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
  useFolders,
  useParticipantFlag,
} from "@/hooks/documents";
import { downloadUrl, useAttachments } from "@/hooks/projects";
import { personName, type Attachment, type DocumentRow } from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import { LIVE_POLL_MS, useNewItemToasts } from "@/hooks/liveRefresh";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { UploadDialog } from "@/pages/project/UploadDialog";
import { FromDriveButton } from "@/components/shared/FromDriveButton";
import { attachFromDrive } from "@/lib/drive";
import { convertible, googleEditor, isImage } from "@/lib/googleFiles";

const isPdf = (a: Attachment) =>
  a.content_type === "application/pdf" || a.original_filename.toLowerCase().endsWith(".pdf");
const previewable = (a: Attachment) => !a.drive_file_id && (isPdf(a) || isImage(a));
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
const rowFlagged = (r: Row) => (r.doc ?? r.file).contains_participant_data;

/** Documents and uploaded files together, in one folder tree. Every server check is unchanged. */
export default function DocumentsTab({ labId, projectId, project }: ProjectTabProps) {
  const navigate = useNavigate();
  const docs = useDocuments(labId, projectId, LIVE_POLL_MS);
  const create = useCreateDocument(labId, projectId);
  const removeDoc = useDeleteDocument(labId, projectId);
  const {
    list: files,
    uploadFile,
    remove: removeFile,
    editInGoogle,
  } = useAttachments(labId, projectId, LIVE_POLL_MS);
  useNewItemToasts(`${projectId}/files`, files.data, "file", (f) => f.original_filename);
  const canEdit = project.my_permissions.includes("edit_content");
  const folder = useCurrentFolder();
  const { data: folders = [] } = useFolders(labId, projectId);
  const folderFlagged = folders.find((f) => f.id === folder)?.contains_participant_data ?? false;
  const flag = useParticipantFlag(labId);
  const toggleFlag = (r: Row) => {
    const value = !rowFlagged(r);
    flag.mutate(
      { kind: r.doc ? "documents" : "attachments", id: rowId(r), value },
      {
        onSuccess: () =>
          toast.success(
            value ? `Marked as identifying participants. ${PARTICIPANT_HINT}` : "No longer marked",
          ),
        onError: (e) => toast.error(formErrors(e, []).form ?? "Something went wrong."),
      },
    );
  };
  const flagLabel = (r: Row) => (rowFlagged(r) ? "Not identifying" : "Mark as identifying");
  const [deleting, setDeleting] = useState<Row | null>(null);
  const [moving, setMoving] = useState<Movable | null>(null);
  const [embedding, setEmbedding] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [previewing, setPreviewing] = useState<Attachment | null>(null);
  const [panel, setPanel] = useState<{ file: Attachment; edit: boolean } | null>(null);
  const panelEditor = panel && googleEditor(panel.file);
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

  const copyToGoogle = (f: Attachment) =>
    editInGoogle.mutate(f.id, {
      onSuccess: (copy) => {
        toast.success("Copied to your Google Drive. Changes there do not change the original.");
        setPanel({ file: copy, edit: true });
      },
      onError: (e) => toast.error(formErrors(e, []).form ?? "Something went wrong."),
    });
  const preview = (f: Attachment) =>
    googleEditor(f) ? setPanel({ file: f, edit: false }) : setPreviewing(f);
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
      className: "w-full max-w-0",
      cell: (r) => (
        <span className="flex items-center gap-2">
          <span className="truncate font-medium" title={rowName(r)}>
            {rowName(r)}
          </span>
          {rowFlagged(r) && <ParticipantBadge />}
        </span>
      ),
    },
    {
      key: "type",
      header: "Type",
      className: HIDE_NARROW,
      cell: (r) => {
        if (r.doc) return "Document";
        const g = googleEditor(r.file);
        const kind = g
          ? g.label
          : r.file.drive_file_id
            ? "Google Drive file"
            : `${isPdf(r.file) ? "PDF" : r.file.content_type || "File"}, ${size(r.file.size_bytes)}`;
        return r.file.source === "link" ? `${kind}, added through Claude` : kind;
      },
    },
    {
      key: "by",
      header: "Last changed by",
      className: HIDE_NARROWER,
      cell: (r) => personName(r.doc ? r.doc.updated_by : r.file.uploaded_by),
    },
    {
      key: "at",
      header: "Updated",
      className: HIDE_NARROW,
      cell: (r) => <RelativeTime value={rowDate(r)} />,
    },
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
          {r.file && (previewable(r.file) || googleEditor(r.file)) && (
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Preview ${rowName(r)}`}
              onClick={() => preview(r.file)}
            >
              <Eye aria-hidden />
            </Button>
          )}
          {canEdit && r.file && googleEditor(r.file) && (
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Edit ${rowName(r)}`}
              onClick={() => setPanel({ file: r.file, edit: true })}
            >
              <Pencil aria-hidden />
            </Button>
          )}
          {canEdit && r.file && convertible(r.file) && (
            <Button
              variant="ghost"
              size="sm"
              disabled={editInGoogle.isPending}
              onClick={() => copyToGoogle(r.file)}
            >
              <Pencil aria-hidden /> Edit in Google
              <span className="sr-only"> ({rowName(r)})</span>
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
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm" aria-label={`More for ${rowName(r)}`}>
                    <MoreHorizontal aria-hidden />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onSelect={() => toggleFlag(r)}>{flagLabel(r)}</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
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
                <DropdownMenuItem onSelect={() => toggleFlag(r)}>{flagLabel(r)}</DropdownMenuItem>
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
    <div className="flex flex-col items-start gap-4 lg:flex-row">
      <div className="grid w-full min-w-0 flex-1 gap-4">
        {canEdit && (
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="outline" onClick={() => setEmbedding(true)}>
              <Link2 className="size-4" /> Embed a document
            </Button>
            <Button variant="outline" onClick={() => setUploading(true)}>
              <Upload aria-hidden /> Upload file
            </Button>
            <FromDriveButton
              labId={labId}
              size="default"
              multiple
              onPick={(f) =>
                attachFromDrive(
                  `/api/labs/${labId}/projects/${projectId}/attachments/`,
                  f.id,
                  folder ? { folder } : {},
                )
              }
            />
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
            else if (googleEditor(r.file) || previewable(r.file)) preview(r.file);
            else if (r.file.external_url) window.open(r.file.external_url, "_blank", "noopener");
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
          participant={folderFlagged}
          send={(file, onProgress, participant) =>
            uploadFile.mutateAsync({ file, onProgress, folder, participant })
          }
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
        {previewing && (
          <FilePreview
            labId={labId}
            file={previewing}
            fullPage={`${base}/files/${previewing.id}`}
            onClose={() => setPreviewing(null)}
          />
        )}
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
      {panel && panelEditor && (
        <GoogleEditorPanel
          title={panel.file.original_filename}
          label={panelEditor.label}
          src={panel.edit ? panelEditor.edit : panelEditor.preview}
          openUrl={panelEditor.edit}
          onClose={() => setPanel(null)}
        />
      )}
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
                maxLength={2000}
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
