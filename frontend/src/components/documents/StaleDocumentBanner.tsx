import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDocuments } from "@/hooks/documents";
import { personName } from "@/lib/api-types";

/** Not real-time co-editing (D145): the project's document list is polled every few seconds (it
 * carries version and last editor, and is not audited as a view). When someone saves a newer
 * version than the one open here, this says who and offers a one-click reload. It never reloads
 * on its own and never touches the editor, so nothing is overwritten silently; a save from a
 * stale copy still gets the 409 conflict dialog (D11, D42). */
export const DOC_POLL_MS = 5000;

export function StaleDocumentBanner({
  labId,
  projectId,
  documentId,
  localVersion,
  dirty,
  onReload,
}: {
  labId: string;
  projectId: string;
  documentId: string;
  /** The version this editor was loaded from or last saved. */
  localVersion: number;
  dirty: boolean;
  onReload: () => void;
}) {
  const { data } = useDocuments(labId, projectId, DOC_POLL_MS);
  const row = data?.find((d) => d.id === documentId);
  if (!row || row.version <= localVersion) return null;
  return (
    <div
      role="status"
      className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-warning bg-warning/15 px-3 py-2 text-sm"
    >
      <span>
        <strong>{personName(row.updated_by)}</strong> updated this document.
        {dirty && " Reloading discards your unsaved changes."}
      </span>
      <Button size="sm" variant="outline" onClick={onReload}>
        <RefreshCw aria-hidden /> Reload
      </Button>
    </div>
  );
}
