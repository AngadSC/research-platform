import { Download, Eye, Paperclip, Trash2, Upload } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
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
  const canEdit = project.my_permissions.includes("edit_content");

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
      cell: (a) => new Date(a.created_at).toLocaleDateString(undefined, { dateStyle: "medium" }),
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
      {(list.data?.length ?? 0) > 0 && <div className="flex justify-end">{uploadBtn}</div>}
      <DataTable
        columns={cols}
        rows={list.data ?? []}
        getRowKey={(a) => a.id}
        loading={list.isLoading}
        empty={
          <EmptyState
            icon={Paperclip}
            title="No files yet"
            description="Add anonymized or aggregate data, protocols and papers for this project. PDFs open right here."
            action={uploadBtn}
          />
        }
      />
      <UploadDialog
        open={uploading}
        onOpenChange={setUploading}
        send={(file, onProgress) => uploadFile.mutateAsync({ file, onProgress })}
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
