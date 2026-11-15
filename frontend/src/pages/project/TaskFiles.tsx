import { FileText, Paperclip, Plus, Upload, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useCreateDocument, useDocuments } from "@/hooks/documents";
import { downloadUrl, useAttachments, useTaskLinks, type TaskLinkKind } from "@/hooks/projects";
import type { Task } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";
import { UploadDialog } from "@/pages/project/UploadDialog";
import { FromDriveButton } from "@/components/shared/FromDriveButton";
import { attachFromDrive } from "@/lib/drive";

const fail = (e: unknown) =>
  toast.error(formErrors(e, ["id"]).fields.id ?? formErrors(e, []).form ?? "Something went wrong.");

/** Documents and files attached to a task (D141): attach existing, create a document, or upload. */
export function TaskFiles({
  labId,
  projectId,
  task,
  canEdit,
}: {
  labId: string;
  projectId: string;
  task: Task;
  canEdit: boolean;
}) {
  const docs = useDocuments(labId, projectId);
  const files = useAttachments(labId, projectId);
  const { attach, detach } = useTaskLinks(labId, projectId, task.id);
  const createDoc = useCreateDocument(labId, projectId);
  const [uploading, setUploading] = useState(false);
  const base = `/labs/${labId}/projects/${projectId}`;

  const linkedDocs = new Set(task.documents.map((d) => d.id));
  const linkedFiles = new Set(task.attachments.map((a) => a.id));
  const freeDocs = (docs.data ?? []).filter((d) => !linkedDocs.has(d.id));
  const freeFiles = (files.list.data ?? []).filter((a) => !linkedFiles.has(a.id));
  const add = (kind: TaskLinkKind, id: string) => attach.mutate({ kind, id }, { onError: fail });
  const remove = (kind: TaskLinkKind, id: string) => detach.mutate({ kind, id }, { onError: fail });

  return (
    <section aria-label="Documents and files" className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Documents and files</h3>
        {canEdit && (
          <div className="flex flex-wrap gap-1">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm">
                  <Paperclip aria-hidden /> Attach existing
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="max-h-72 overflow-y-auto">
                {freeDocs.length + freeFiles.length === 0 && (
                  <DropdownMenuLabel>Nothing else in this project</DropdownMenuLabel>
                )}
                {freeDocs.length > 0 && <DropdownMenuLabel>Documents</DropdownMenuLabel>}
                {freeDocs.map((d) => (
                  <DropdownMenuItem key={d.id} onSelect={() => add("documents", d.id)}>
                    {d.title}
                  </DropdownMenuItem>
                ))}
                {freeDocs.length > 0 && freeFiles.length > 0 && <DropdownMenuSeparator />}
                {freeFiles.length > 0 && <DropdownMenuLabel>Files</DropdownMenuLabel>}
                {freeFiles.map((a) => (
                  <DropdownMenuItem key={a.id} onSelect={() => add("attachments", a.id)}>
                    {a.original_filename}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            <Button
              variant="outline"
              size="sm"
              disabled={createDoc.isPending}
              onClick={() =>
                createDoc.mutate(`Notes: ${task.title}`.slice(0, 300), {
                  onSuccess: (d) => add("documents", d.id),
                  onError: fail,
                })
              }
            >
              <Plus aria-hidden /> New document
            </Button>
            <Button variant="outline" size="sm" onClick={() => setUploading(true)}>
              <Upload aria-hidden /> Upload file
            </Button>
            <FromDriveButton
              labId={labId}
              onPick={async (f) => {
                const a = await attachFromDrive(
                  `/api/labs/${labId}/projects/${projectId}/attachments/`,
                  f.id,
                );
                await attach.mutateAsync({ kind: "attachments", id: a.id });
              }}
            />
          </div>
        )}
      </div>
      {task.documents.length + task.attachments.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nothing attached yet.</p>
      ) : (
        <ul className="grid divide-y rounded-md border bg-background">
          {task.documents.map((d) => (
            <li key={d.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
              <Link
                to={`${base}/documents/${d.id}`}
                className="flex min-w-0 items-center gap-2 hover:underline"
              >
                <FileText aria-hidden className="size-4 shrink-0" />
                <span className="truncate">{d.title}</span>
              </Link>
              {canEdit && (
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Detach ${d.title}`}
                  onClick={() => remove("documents", d.id)}
                >
                  <X aria-hidden />
                </Button>
              )}
            </li>
          ))}
          {task.attachments.map((a) => (
            <li key={a.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
              <a
                href={downloadUrl(labId, a.id)}
                download
                className="flex min-w-0 items-center gap-2 hover:underline"
              >
                <Paperclip aria-hidden className="size-4 shrink-0" />
                <span className="truncate">{a.original_filename}</span>
              </a>
              {canEdit && (
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Detach ${a.original_filename}`}
                  onClick={() => remove("attachments", a.id)}
                >
                  <X aria-hidden />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <UploadDialog
        open={uploading}
        onOpenChange={setUploading}
        participant={false}
        send={async (file, onProgress, participant) => {
          const a = await files.uploadFile.mutateAsync({ file, onProgress, participant });
          await attach.mutateAsync({ kind: "attachments", id: a.id });
        }}
      />
    </section>
  );
}
