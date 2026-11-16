import { useState } from "react";
import { Link } from "react-router";
import { MessagesSquare } from "lucide-react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { KIND_LABEL, useGoogleChat, useGoogleChatSpaces } from "@/hooks/googleChat";
import { cn } from "@/lib/utils";
import { formErrors } from "@/lib/forms";
import { GoogleChatImportDialog } from "@/pages/GoogleChatImport";

/** A chat's Google Chat link: the lab chat's (D318) or, with `projectId`, a project chat's
 * (D325). A line everyone in the chat sees, and for whoever may link it the controls to pick a
 * space, group chat or direct message, or stop syncing. `compact` fits a side panel. */
export function GoogleChatSync({
  labId,
  projectId,
  compact,
}: {
  labId: string;
  projectId?: string;
  compact?: boolean;
}) {
  const { status, unlink } = useGoogleChat(labId, projectId);
  const [picking, setPicking] = useState(false);
  const [importing, setImporting] = useState(false); // D327
  const s = status.data;
  if (!s || (!s.bridge && !(s.can_manage && s.configured))) return null;
  const integrations = `/labs/${labId}/settings/integrations`;

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-x-3 gap-y-1 text-sm",
        compact ? "border-b px-3 py-2" : "mb-3 rounded-lg border bg-card px-3 py-2",
      )}
    >
      <MessagesSquare className="size-4 text-muted-foreground" aria-hidden />
      {s.bridge ? (
        <>
          <span>
            Synced with Google Chat:{" "}
            <span className="font-medium">{s.bridge.space_name || "a conversation"}</span>
          </span>
          {!s.connected && (
            <span className="text-muted-foreground">
              <Link to={integrations} className="underline underline-offset-2">
                Connect Google Chat
              </Link>{" "}
              to post there as yourself.
            </span>
          )}
          {s.can_manage && s.bridge.last_error && (
            <span role="status" className="text-destructive">
              {s.bridge.last_error}
            </span>
          )}
          {s.can_manage && (
            <span className="ml-auto flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => setImporting(true)}>
                Import messages
              </Button>
              <Button size="sm" variant="outline" onClick={() => setPicking(true)}>
                Change
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={unlink.isPending}
                onClick={() =>
                  unlink.mutate(undefined, {
                    onSuccess: () => toast.success("Stopped syncing with Google Chat"),
                    onError: (e) => toast.error(formErrors(e, []).form ?? "Could not stop it."),
                  })
                }
              >
                Stop syncing
              </Button>
            </span>
          )}
        </>
      ) : (
        <>
          {!compact && (
            <span className="text-muted-foreground">
              Keep this chat and a Google Chat conversation in step.
            </span>
          )}
          <span className="ml-auto flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => setImporting(true)}>
              Import messages
            </Button>
            <Button size="sm" variant="outline" onClick={() => setPicking(true)}>
              Sync with Google Chat
            </Button>
          </span>
        </>
      )}
      {importing && (
        <GoogleChatImportDialog
          labId={labId}
          projectId={projectId}
          connected={s.connected}
          onClose={() => setImporting(false)}
        />
      )}
      {picking && (
        <PickSpaceDialog
          labId={labId}
          projectId={projectId}
          connected={s.connected}
          current={s.bridge?.space}
          integrations={integrations}
          onClose={() => setPicking(false)}
        />
      )}
    </div>
  );
}

function PickSpaceDialog({
  labId,
  projectId,
  connected,
  current,
  integrations,
  onClose,
}: {
  labId: string;
  projectId?: string;
  connected: boolean;
  current?: string;
  integrations: string;
  onClose: () => void;
}) {
  const { link } = useGoogleChat(labId, projectId);
  const spaces = useGoogleChatSpaces(labId, connected, projectId);
  const [space, setSpace] = useState(current ?? "");
  const error = spaces.error ?? link.error;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">Sync with Google Chat</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          Messages sent from now on appear in both places. Pick a space, a group chat or a direct
          message; each can feed only one chat here. Members who connect Google Chat post there as
          themselves; everyone else is posted through your connection, with their name first. Google
          Chat works only with Google Workspace accounts.
        </DialogDescription>
        {!connected ? (
          <p className="text-sm">
            First{" "}
            <Link to={integrations} className="underline underline-offset-2">
              connect Google Chat
            </Link>{" "}
            in Integrations, then come back here.
          </p>
        ) : (
          <div className="grid gap-2">
            <Label htmlFor="gchat-space">Conversation</Label>
            <Select value={space} onValueChange={setSpace} disabled={spaces.isLoading}>
              <SelectTrigger id="gchat-space">
                <SelectValue
                  placeholder={spaces.isLoading ? "Loading conversations…" : "Pick a conversation"}
                />
              </SelectTrigger>
              <SelectContent>
                {(spaces.data ?? []).map((sp) => (
                  <SelectItem key={sp.name} value={sp.name}>
                    {sp.display_name || sp.name}
                    <span className="ml-2 text-xs text-muted-foreground">
                      {KIND_LABEL[sp.kind]}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {spaces.data?.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Your Google account is in no conversations yet.
              </p>
            )}
          </div>
        )}
        {error && <FormError message={formErrors(error, []).form} />}
        <div className="flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button
            disabled={!connected || !space || link.isPending}
            onClick={() =>
              link.mutate(space, {
                onSuccess: () => {
                  toast.success("This chat now syncs with Google Chat");
                  onClose();
                },
              })
            }
          >
            Start syncing
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
