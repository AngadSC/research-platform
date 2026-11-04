import { lazy, Suspense, useState } from "react";
import { toast } from "sonner";
import { DetailPanel } from "@/components/shared/DetailPanel";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useRestoreRevision, useRevision, useRevisions } from "@/hooks/documents";
import { personName } from "@/lib/api-types";
import { when } from "@/lib/format";
import { formErrors } from "@/lib/forms";
import { cn } from "@/lib/utils";

const RichEditor = lazy(() => import("./RichEditor"));

/** Read-only preview of one saved version. */
export function RevisionPreview({
  labId,
  documentId,
  version,
}: {
  labId: string;
  documentId: string;
  version: number;
}) {
  const { data } = useRevision(labId, documentId, version);
  if (!data) return <Skeleton aria-label="Loading version" className="h-32 w-full" />;
  return (
    <Suspense fallback={<Skeleton className="h-32 w-full" />}>
      <RichEditor
        key={version}
        initialContent={(data.content as unknown[]) ?? []}
        editable={false}
        label={`Version ${version} preview`}
      />
    </Suspense>
  );
}

interface Props {
  labId: string;
  documentId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  canEdit: boolean;
  hasUnsaved: boolean;
  /** Called after a successful restore so the page can load the new version. */
  onRestored: () => void;
}

export function RevisionsPanel({
  labId,
  documentId,
  open,
  onOpenChange,
  canEdit,
  hasUnsaved,
  onRestored,
}: Props) {
  const { data: revisions, isLoading } = useRevisions(labId, documentId, open);
  const restore = useRestoreRevision(labId, documentId);
  const [selected, setSelected] = useState<number | null>(null);
  const [confirming, setConfirming] = useState(false);

  const doRestore = () =>
    selected !== null &&
    restore.mutate(selected, {
      onSuccess: (doc) => {
        toast.success(`Restored as version ${doc.version}`);
        setConfirming(false);
        setSelected(null);
        onOpenChange(false);
        onRestored();
      },
      onError: (e) => {
        setConfirming(false);
        toast.error(formErrors(e, []).form ?? "Something went wrong.");
      },
    });

  return (
    <DetailPanel
      open={open}
      onOpenChange={onOpenChange}
      title="Revisions"
      description="Every save is kept. Select a version to preview it."
    >
      <div className="flex flex-col gap-4">
        {isLoading && <Skeleton className="h-24 w-full" />}
        <ul className="flex flex-col gap-1">
          {revisions?.map((r) => (
            <li key={r.id}>
              <button
                type="button"
                aria-pressed={selected === r.version}
                onClick={() => setSelected(r.version)}
                className={cn(
                  "w-full rounded-md border px-3 py-2 text-left text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                  selected === r.version ? "border-primary bg-secondary" : "hover:bg-secondary",
                )}
              >
                <span className="font-medium">Version {r.version}</span>
                <span className="block text-xs text-muted-foreground">
                  {personName(r.created_by)}, {when(r.created_at)}
                </span>
              </button>
            </li>
          ))}
        </ul>
        {selected !== null && (
          <div className="flex flex-col gap-3">
            <RevisionPreview labId={labId} documentId={documentId} version={selected} />
            {canEdit && (
              <Button variant="outline" onClick={() => setConfirming(true)}>
                Restore this version
              </Button>
            )}
          </div>
        )}
      </div>
      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">Restore version {selected}?</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            This saves version {selected} as a new version. Nothing is lost: the current version
            stays in the history.
            {hasUnsaved && " Your unsaved changes in the editor will be discarded."}
          </DialogDescription>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button disabled={restore.isPending} onClick={doRestore}>
              Restore
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </DetailPanel>
  );
}
