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
import { useGoogleChat, useGoogleChatSpaces } from "@/hooks/googleChat";
import { formErrors } from "@/lib/forms";

/** The lab chat's Google Chat link (D318): a line every member sees, and for PIs and lab admins
 * the controls to pick a space or stop syncing. */
export function GoogleChatSync({ labId }: { labId: string }) {
  const { status, unlink } = useGoogleChat(labId);
  const [picking, setPicking] = useState(false);
  const s = status.data;
  if (!s || (!s.bridge && !(s.can_manage && s.configured))) return null;
  const integrations = `/labs/${labId}/settings/integrations`;

  return (
    <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border bg-card px-3 py-2 text-sm">
      <MessagesSquare className="size-4 text-muted-foreground" aria-hidden />
      {s.bridge ? (
        <>
          <span>
            Synced with Google Chat:{" "}
            <span className="font-medium">{s.bridge.space_name || "a space"}</span>
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
            <span className="ml-auto flex gap-2">
              <Button size="sm" variant="outline" onClick={() => setPicking(true)}>
                Change space
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
          <span className="text-muted-foreground">
            Keep this chat and a Google Chat space in step.
          </span>
          <Button size="sm" variant="outline" className="ml-auto" onClick={() => setPicking(true)}>
            Sync with Google Chat
          </Button>
        </>
      )}
      {picking && (
        <PickSpaceDialog
          labId={labId}
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
  connected,
  current,
  integrations,
  onClose,
}: {
  labId: string;
  connected: boolean;
  current?: string;
  integrations: string;
  onClose: () => void;
}) {
  const { link } = useGoogleChat(labId);
  const spaces = useGoogleChatSpaces(labId, connected);
  const [space, setSpace] = useState(current ?? "");
  const error = spaces.error ?? link.error;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">Sync with Google Chat</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          Messages sent from now on appear in both places. Members who connect Google Chat post
          there as themselves; everyone else is posted through your connection, with their name
          first. Google Chat works only with Google Workspace accounts.
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
            <Label htmlFor="gchat-space">Space</Label>
            <Select value={space} onValueChange={setSpace} disabled={spaces.isLoading}>
              <SelectTrigger id="gchat-space">
                <SelectValue placeholder={spaces.isLoading ? "Loading spaces…" : "Pick a space"} />
              </SelectTrigger>
              <SelectContent>
                {(spaces.data ?? []).map((sp) => (
                  <SelectItem key={sp.name} value={sp.name}>
                    {sp.display_name || sp.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {spaces.data?.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Your Google account is in no named spaces. Create one in Google Chat first.
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
                  toast.success("The lab chat now syncs with Google Chat");
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
