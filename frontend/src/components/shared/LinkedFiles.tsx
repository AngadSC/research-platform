import { HardDrive, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { ExternalLinkItem } from "@/components/shared/ExternalLinkItem";
import { Button } from "@/components/ui/button";
import {
  fetchPickerToken,
  useAcceptExternalChange,
  useCheckExternalLink,
  useCreateExternalLink,
  useExternalLinks,
  useProviders,
  useRemoveExternalLink,
} from "@/hooks/integrations";
import { ApiError } from "@/lib/api";
import type { ExternalLink } from "@/lib/api-types";
import { pickDriveFile } from "@/lib/drive";
import { formErrors } from "@/lib/forms";

export type LinkTarget = "dataset" | "analysis" | "result" | "manuscript";
const DRIVE = "google_drive";
const NOTES: Record<string, string> = {
  copied: "The file's checksum was added to this record.",
  kept: "This record already has a different version, so it was left as it is. Add a new version to record this one.",
};

/** "Link from Google Drive": opens Google's Picker (loaded on click) and links the file. Not
 * rendered when Drive is not set up for the lab. */
export function DriveLinkButton({
  labId,
  projectId,
  target,
}: {
  labId: string;
  projectId: string;
  target?: { field: LinkTarget; id: string };
}) {
  const provider = useProviders(labId).data?.find((p) => p.name === DRIVE);
  const create = useCreateExternalLink(labId, projectId);
  const [busy, setBusy] = useState(false);
  const config = provider?.public_config;
  if (!provider?.configured || !config?.api_key || !config.app_id) return null;
  const apiKey = config.api_key;
  const appId = config.app_id;

  const start = async () => {
    if (provider.account?.status !== "active") {
      toast.error("Connect Google Drive first, under Settings > Integrations.");
      return;
    }
    setBusy(true);
    try {
      const { access_token: token } = await fetchPickerToken(labId);
      const file = await pickDriveFile({ apiKey, appId, token });
      if (!file) return;
      const link = await create.mutateAsync({
        provider: DRIVE,
        external_id: file.id,
        ...(target ? { [target.field]: target.id } : {}),
      });
      const note = NOTES[link.version_note ?? ""];
      toast.success(`Linked ${link.title}`, note ? { description: note } : undefined);
    } catch (e) {
      // A failed Picker load is a plain Error; API errors carry the server's message.
      toast.error(e instanceof ApiError ? formErrors(e, []).form : (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button variant="outline" disabled={busy} onClick={() => void start()}>
      <HardDrive aria-hidden /> Link from Google Drive
    </Button>
  );
}

/** The outside files linked to one item (or, with no target, to the project itself), each with
 * Refresh, Accept change and Remove. */
export function LinkedFiles({
  labId,
  projectId,
  target,
  canEdit,
}: {
  labId: string;
  projectId: string;
  target?: { field: LinkTarget; id: string };
  canEdit: boolean;
}) {
  const links = useExternalLinks(labId, projectId);
  const check = useCheckExternalLink(labId, projectId);
  const accept = useAcceptExternalChange(labId, projectId);
  const remove = useRemoveExternalLink(labId, projectId);
  const fail = (e: unknown) => toast.error(formErrors(e, []).form ?? "Something went wrong.");

  const mine = (links.data ?? []).filter((l: ExternalLink) =>
    target
      ? l[target.field] === target.id
      : !l.document && !l.dataset && !l.analysis && !l.result && !l.manuscript,
  );

  return (
    <div className="grid gap-2">
      {canEdit && <DriveLinkButton labId={labId} projectId={projectId} target={target} />}
      {mine.length > 0 && (
        <>
          <ul className="grid divide-y rounded-lg border bg-background">
            {mine.map((l) => (
              <ExternalLinkItem
                key={l.id}
                link={l}
                actions={
                  <>
                    {!l.check_blocked && (
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Refresh ${l.title}`}
                        disabled={check.isPending}
                        onClick={() =>
                          check.mutate(l.id, {
                            onSuccess: () => toast.success("Checked"),
                            onError: fail,
                          })
                        }
                      >
                        <RefreshCw aria-hidden /> Refresh
                      </Button>
                    )}
                    {canEdit && l.changed_since_linked && !l.unavailable_since && (
                      <Button
                        variant="outline"
                        size="sm"
                        aria-label={`Accept change to ${l.title}`}
                        disabled={accept.isPending}
                        onClick={() =>
                          accept.mutate(l.id, {
                            onSuccess: () => toast.success("Change accepted"),
                            onError: fail,
                          })
                        }
                      >
                        Accept change
                      </Button>
                    )}
                    {canEdit && (
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Remove link to ${l.title}`}
                        onClick={() =>
                          remove.mutate(l.id, {
                            onSuccess: () => toast.success("Link removed"),
                            onError: fail,
                          })
                        }
                      >
                        <Trash2 aria-hidden />
                      </Button>
                    )}
                  </>
                }
              />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
