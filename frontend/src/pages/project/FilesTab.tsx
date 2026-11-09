import { Download, Eye, FolderInput, Paperclip, Trash2, Upload } from "lucide-react";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { FolderBrowser, MoveDialog, type Movable } from "@/components/documents/Folders";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { LinkedFiles } from "@/components/shared/LinkedFiles";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { useCurrentFolder } from "@/hooks/documents";
import { downloadUrl, useAttachments } from "@/hooks/projects";
import { personName, type Attachment } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";
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

export default function FilesTab({ labId, projectId, project }: ProjectTabProps) {
  const { list, uploadFile, remove } = useAttachments(labId, projectId);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState<Attachment | null>(null);
  const [moving, setMoving] = useState<Movable | null>(null);
  const canEdit = project.my_permissions.includes("edit_content");
  const folder = useCurrentFolder();
  const rows = (list.data ?? []).filter((a) => (a.folder ?? null) === folder);

  const cols: Column<Attachment>[] = [
    {
      key: "name",
      header: "Name",
      cell: (a) => <span className="font-medium">{a.original_filename}</span>,
    },
    { key: "type", header: "Type", cell: (a) => (isPdf(a) ? "PDF" : a.content_type || "File") },
    { key: "size", header: "Size", cell: (a) => size(a.size_bytes) },
    { key: "by", header: "Uploaded by", cell: (a) => personName(a.uploaded_by) },
    {
      key: "date",
      header: "Date",
      cell: (a) => <RelativeTime value={a.created_at} />,
    },
    {
      key: "actions",
      header: "Actions",
      className: "text-right",
      cell: (a) => (
        <div className="flex justify-end gap-1">
          {isPdf(a) && (
            <Button variant="ghost" size="sm" asChild>
              <Link to={a.id} aria-label={`Open ${a.original_filename}`}>
                <Eye aria-hidden />
              </Link>
            </Button>
          )}
          <Button variant="ghost" size="sm" asChild>
            <a
              href={downloadUrl(labId, a.id)}
              download
              aria-label={`Download ${a.original_filename}`}
            >
              <Download aria-hidden />
            </a>
          </Button>
          {canEdit && (
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Move ${a.original_filename}`}
              onClick={() =>
                setMoving({
                  kind: "attachments",
                  id: a.id,
                  name: a.original_filename,
                  folder: a.folder ?? null,
                })
              }
            >
              <FolderInput aria-hidden />
            </Button>
          )}
          {canEdit && (
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Delete ${a.original_filename}`}
              onClick={() => setDeleting(a)}
            >
              <Trash2 aria-hidden />
            </Button>
          )}
        </div>
      ),
    },
  ];

  const uploadBtn = canEdit ? (
    <Button onClick={() => setUploading(true)}>
      <Upload aria-hidden /> Upload file
    </Button>
  ) : undefined;

  return (
    <div className="grid gap-4">
      {canEdit && <div className="flex justify-end">{uploadBtn}</div>}
      <FolderBrowser labId={labId} projectId={projectId} canEdit={canEdit} />
      <DataTable
        columns={cols}
        rows={rows}
        getRowKey={(a) => a.id}
        loading={list.isLoading}
        empty={
          <EmptyState
            icon={Paperclip}
            title={folder ? "No files in this folder" : "No files yet"}
            description="Add anonymized or aggregate data, protocols and papers for this project. PDFs open right here."
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
      <Dialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">
            Delete {deleting?.original_filename}?
          </DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            The file will be removed from this project.
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
                  onSuccess: () => toast.success("File deleted"),
                  onError: (e) => toast.error(formErrors(e, []).form ?? "Something went wrong."),
                  onSettled: () => setDeleting(null),
                })
              }
            >
              Delete file
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
