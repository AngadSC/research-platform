import { Eye, FileText, Link2, MoreHorizontal, Pencil, Plus, Upload } from "lucide-react";
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
import {
  MARKED_TOAST,
  ParticipantBadge,
  markLabel,
  useConfirmUnmark,
} from "@/components/shared/ParticipantData";
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

/** "Word", "CSV", "PDF"... from the name or type, instead of the raw type string. */
function kindOf(a: Attachment): string {
  if (isPdf(a)) return "PDF";
  const ext = /\.([a-z0-9]+)$/i.exec(a.original_filename)?.[1]?.toLowerCase() ?? "";
  const named: Record<string, string> = {
    docx: "Word",
    doc: "Word",
    xlsx: "Excel",
    xls: "Excel",
    pptx: "PowerPoint",
    ppt: "PowerPoint",
    csv: "CSV",
    txt: "Text",
    md: "Text",
    json: "JSON",
    zip: "Zip",
  };
  if (named[ext]) return named[ext]!;
  if (a.content_type.startsWith("image/")) return "Image";
  if (a.content_type === "text/csv") return "CSV";
  if (a.content_type.startsWith("text/")) return "Text";
  return ext ? ext.toUpperCase() : "File";
}

/** A browser download that never navigates away, for files with no preview. */
function startDownload(href: string) {
  const a = document.createElement("a");
  a.href = href;
  a.download = "";
  a.click();
}

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
  const { confirm, dialog } = useConfirmUnmark();
  const toggleFlag = (r: Row) => {
    const value = !rowFlagged(r);
    flag.mutate(
      { kind: r.doc ? "documents" : "attachments", id: rowId(r), value },
      {
        onSuccess: () => toast.success(value ? MARKED_TOAST : "Identifying mark removed"),
        onError: (e) => toast.error(formErrors(e, []).form ?? "Something went wrong."),
      },
    );
  };
  const [deleting, setDeleting] = useState<Row | null>(null);
  const [deleteError, setDeleteError] = useState<string>();
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
      onSuccess: () => {
        toast.success(deleting.doc ? "Document deleted" : "File deleted");
        setDeleting(null);
      },
      // Stay open so the person sees why and can try again.
      onError: (e: unknown) =>
        setDeleteError(formErrors(e, []).form ?? "Something went wrong. Try again."),
    };
    setDeleteError(undefined);
    if (deleting.doc) removeDoc.mutate(deleting.doc.id, done);
    else removeFile.mutate(deleting.file.id, done);
  };

  const originals = new Map((files.data ?? []).map((f) => [f.id, f.original_filename]));
  const cols: Column<Row>[] = [
    {
      key: "name",
      header: "Name",
      className: "w-full max-w-0 min-w-44",
      cell: (r) => {
        const original = r.file?.copied_from && originals.get(r.file.copied_from);
        return (
          <span className="grid min-w-0 justify-items-start gap-0.5">
            <span className="max-w-full truncate font-medium" title={rowName(r)}>
              {rowName(r)}
            </span>
            {original && (
              <span className="max-w-full truncate text-xs text-muted-foreground">
                Google copy of {original}
              </span>
            )}
            {rowFlagged(r) && <ParticipantBadge />}
          </span>
        );
      },
    },
    {
      key: "type",
      header: "Type",
      className: `${HIDE_NARROW} whitespace-nowrap`,
      cell: (r) => {
        if (r.doc) return "Document";
        const g = googleEditor(r.file);
        const kind = g
          ? g.label
          : r.file.drive_file_id
            ? "Google Drive file"
            : `${kindOf(r.file)} · ${size(r.file.size_bytes)}`;
        return r.file.source === "link" ? `${kind}, added through Claude` : kind;
      },
    },
    {
      key: "by",
      header: "Last changed by",
      className: `${HIDE_NARROWER} whitespace-nowrap`,
      cell: (r) => personName(r.doc ? r.doc.updated_by : r.file.uploaded_by),
    },
    {
      key: "at",
      header: "Updated",
      className: `${HIDE_NARROW} whitespace-nowrap`,
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
          {(r.file || canEdit) && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" aria-label={`Actions for ${rowName(r)}`}>
                  <MoreHorizontal aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {r.file && (
                  <DropdownMenuItem asChild>
                    <a href={downloadUrl(labId, r.file.id)} download>
                      Download
                    </a>
                  </DropdownMenuItem>
                )}
                {canEdit && r.file && convertible(r.file) && (
                  <DropdownMenuItem
                    disabled={editInGoogle.isPending}
                    onSelect={() => copyToGoogle(r.file)}
                  >
                    Edit in Google
                  </DropdownMenuItem>
                )}
                {canEdit && (
                  <>
                    <DropdownMenuItem onSelect={() => startMove(r)}>
                      Move to folder
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onSelect={() => confirm(rowFlagged(r), rowName(r), () => toggleFlag(r))}
                    >
                      {markLabel(rowFlagged(r))}
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onSelect={() => {
                        setDeleteError(undefined);
                        setDeleting(r);
                      }}
                    >
                      Delete
                    </DropdownMenuItem>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      ),
    },
  ];

  const noun = deleting?.doc ? "document" : "file";
  return (
    <div>
      {dialog}
      <div className="grid w-full min-w-0 gap-4">
        {canEdit && (
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="outline" onClick={() => setEmbedding(true)}>
              <Link2 className="size-4" /> Embed a Google or Office doc
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
            else startDownload(downloadUrl(labId, r.file.id));
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
        <Dialog
          open={!!deleting}
          onOpenChange={(o) => {
            if (!o) {
              setDeleting(null);
              setDeleteError(undefined);
            }
          }}
        >
          <DialogContent>
            <DialogTitle className="text-base font-semibold">
              Delete {deleting && rowName(deleting)}?
            </DialogTitle>
            <DialogDescription className="text-sm text-muted-foreground">
              The {noun} will be removed from this project.
              {deleting?.file?.drive_file_id &&
                " It stays in your Google Drive; nothing is deleted there."}
            </DialogDescription>
            <FormError message={deleteError} />
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
        <DialogTitle className="text-base font-semibold">Embed a Google or Office doc</DialogTitle>
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
