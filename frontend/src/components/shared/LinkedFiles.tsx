import { RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { ExternalLinkItem } from "@/components/shared/ExternalLinkItem";
import { LinkMenu, type LinkTargetRef } from "@/components/shared/LinkMenu";
import { Button } from "@/components/ui/button";
import {
  useAcceptExternalChange,
  useCheckExternalLink,
  useExternalLinks,
  useRemoveExternalLink,
} from "@/hooks/integrations";
import type { ExternalLink } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";

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
  target?: LinkTargetRef;
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
      : !l.document && !l.dataset && !l.analysis && !l.result && !l.manuscript && !l.decision,
  );

  return (
    <div className="grid gap-2">
      {canEdit && <LinkMenu labId={labId} projectId={projectId} target={target} />}
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
