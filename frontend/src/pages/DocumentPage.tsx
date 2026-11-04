import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useBlocker, useParams } from "react-router";
import { toast } from "sonner";
import { ConflictDialog } from "@/components/documents/ConflictDialog";
import { RevisionsPanel } from "@/components/documents/RevisionsPanel";
import { FormError } from "@/components/shared/FormError";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useDocument, useSaveDocument } from "@/hooks/documents";
import { useProject } from "@/hooks/projects";
import { ApiError } from "@/lib/api";
import type { DocumentConflict, DocumentFull } from "@/lib/api-types";
import { blocksToText } from "@/lib/blocks";
import { formErrors } from "@/lib/forms";

const RichEditor = lazy(() => import("@/components/documents/RichEditor"));

function DocumentEditor({
  doc,
  labId,
  canEdit,
  onReload,
}: {
  doc: DocumentFull;
  labId: string;
  canEdit: boolean;
  onReload: () => Promise<void>;
}) {
  const save = useSaveDocument(labId, doc.id);
  const [title, setTitle] = useState(doc.title);
  const [dirty, setDirty] = useState(false);
  const [conflict, setConflict] = useState<DocumentConflict | null>(null);
  const [history, setHistory] = useState(false);
  const [initial] = useState<unknown[]>(() => (Array.isArray(doc.content) ? doc.content : []));
  const content = useRef<unknown[]>(initial);
  const version = useRef(doc.version);

  const send = useCallback(
    (baseVersion: number) =>
      save.mutate(
        {
          title: title.trim() || "Untitled document",
          content: content.current,
          base_version: baseVersion,
        },
        {
          onSuccess: (d) => {
            version.current = d.version;
            setDirty(false);
            setConflict(null);
            toast.success("Saved");
          },
          onError: (e) => {
            if (e instanceof ApiError && e.status === 409) setConflict(e.body as DocumentConflict);
            else toast.error(formErrors(e, []).form ?? "Something went wrong.");
          },
        },
      ),
    [save, title],
  );
  const doSave = useCallback(() => {
    if (canEdit) send(version.current);
  }, [canEdit, send]);

  // Cmd/Ctrl+S saves instead of the browser's "save page" dialog.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        doSave();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [doSave]);

  // Leaving with unsaved changes: in-app (router blocker) and tab close (beforeunload).
  const blocker = useBlocker(dirty);
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const reload = async () => {
    setDirty(false);
    setConflict(null);
    await onReload();
  };
  const copyAndReload = async (format: "json" | "text") => {
    const text =
      format === "json"
        ? JSON.stringify({ title, content: content.current }, null, 2)
        : `${title}\n\n${blocksToText(content.current)}`;
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Your changes were copied");
    } catch {
      toast.error("Could not copy to the clipboard. Your changes were not discarded.");
      return;
    }
    await reload();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <Input
          aria-label="Title"
          value={title}
          readOnly={!canEdit}
          maxLength={200}
          className="h-11 flex-1 text-xl font-semibold"
          onChange={(e) => {
            setTitle(e.target.value);
            setDirty(true);
          }}
        />
        {dirty && <span className="text-xs text-muted-foreground">Unsaved changes</span>}
        <Button variant="outline" onClick={() => setHistory(true)}>
          History
        </Button>
        {canEdit && (
          <Button disabled={save.isPending || !dirty} onClick={doSave}>
            Save
          </Button>
        )}
      </div>
      {!canEdit && (
        <p className="text-xs text-muted-foreground">You have read-only access to this document.</p>
      )}
      <Suspense fallback={<Skeleton className="h-64 w-full" />}>
        <RichEditor
          initialContent={initial}
          editable={canEdit}
          label="Document content"
          onChange={(b) => {
            content.current = b;
            setDirty(true);
          }}
        />
      </Suspense>
      <ConflictDialog
        conflict={conflict}
        labId={labId}
        documentId={doc.id}
        saving={save.isPending}
        onCopyAndReload={(f) => void copyAndReload(f)}
        onOverwrite={() => conflict && send(conflict.current_version)}
        onDismiss={() => setConflict(null)}
      />
      <RevisionsPanel
        labId={labId}
        documentId={doc.id}
        open={history}
        onOpenChange={setHistory}
        canEdit={canEdit}
        hasUnsaved={dirty}
        onRestored={() => void reload()}
      />
      <Dialog open={blocker.state === "blocked"} onOpenChange={(o) => !o && blocker.reset?.()}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">Leave without saving?</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            You have unsaved changes. If you leave now they will be lost.
          </DialogDescription>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => blocker.reset?.()}>
              Stay
            </Button>
            <Button variant="destructive" onClick={() => blocker.proceed?.()}>
              Leave
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function DocumentPage() {
  const { labId = "", projectId = "", documentId = "" } = useParams();
  const { data: project } = useProject(labId, projectId);
  const { data: doc, error, refetch } = useDocument(labId, documentId);
  const [epoch, setEpoch] = useState(0);
  // A fresh editor per load, so reloads and restores replace the editor's content.
  const reload = useMemo(
    () => async () => {
      await refetch();
      setEpoch((n) => n + 1);
    },
    [refetch],
  );

  if (error) return <FormError message={formErrors(error, []).form} />;
  if (!doc || !project)
    return (
      <div aria-busy="true" aria-label="Loading" className="grid gap-3">
        <Skeleton className="h-11 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  return (
    <DocumentEditor
      key={`${doc.id}-${epoch}`}
      doc={doc}
      labId={labId}
      canEdit={project.my_permissions.includes("edit_content")}
      onReload={reload}
    />
  );
}
