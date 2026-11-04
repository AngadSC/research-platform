import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import type { DocumentConflict } from "@/lib/api-types";
import { personName } from "@/lib/api-types";
import { when } from "@/lib/format";
import { RevisionPreview } from "./RevisionsPanel";

interface Props {
  conflict: DocumentConflict | null;
  labId: string;
  documentId: string;
  saving: boolean;
  /** Copy my changes ("json" or "text"), then reload the server version. */
  onCopyAndReload: (format: "json" | "text") => void;
  /** Explicit overwrite: re-send my changes on top of the server's current version. */
  onOverwrite: () => void;
  onDismiss: () => void;
}

/** D11: never overwrite silently. The user picks what happens to their changes. */
export function ConflictDialog({
  conflict,
  labId,
  documentId,
  saving,
  onCopyAndReload,
  onOverwrite,
  onDismiss,
}: Props) {
  const [viewing, setViewing] = useState(false);
  return (
    <Dialog open={!!conflict} onOpenChange={(o) => !o && onDismiss()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogTitle className="text-base font-semibold">
          This document changed since you opened it
        </DialogTitle>
        {conflict && (
          <>
            <DialogDescription className="text-sm text-muted-foreground">
              {personName(conflict.updated_by)} saved version {conflict.current_version} on{" "}
              {when(conflict.updated_at)}. Your changes have not been saved.
            </DialogDescription>
            {viewing && (
              <RevisionPreview
                labId={labId}
                documentId={documentId}
                version={conflict.current_version}
              />
            )}
            <div className="flex flex-wrap justify-end gap-2">
              <Button variant="outline" onClick={() => setViewing((v) => !v)}>
                {viewing ? "Hide their version" : "View their version"}
              </Button>
              <Button variant="outline" onClick={() => onCopyAndReload("json")}>
                Copy my changes as JSON and reload
              </Button>
              <Button variant="outline" onClick={() => onCopyAndReload("text")}>
                Copy my changes as text and reload
              </Button>
              <Button variant="destructive" disabled={saving} onClick={onOverwrite}>
                Save anyway (overwrite theirs)
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
