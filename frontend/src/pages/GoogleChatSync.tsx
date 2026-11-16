import { useState, type ReactNode } from "react";
import { Link } from "react-router";
import {
  CircleCheck,
  Download,
  Ellipsis,
  MessagesSquare,
  Plug,
  RefreshCw,
  Repeat,
  TriangleAlert,
  Unlink,
} from "lucide-react";
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
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

  const stop = () =>
    unlink.mutate(undefined, {
      onSuccess: () => toast.success("Stopped syncing with Google Chat"),
      onError: (e) => toast.error(formErrors(e, []).form ?? "Could not stop it."),
    });
  const name = s.bridge?.space_name || "a conversation";
  const problem = s.can_manage && s.bridge?.last_error;

  return (
    <TooltipProvider>
      <div
        className={cn(
          "flex items-center gap-2 text-sm",
          compact ? "border-b px-3 py-1.5" : "mb-3 rounded-lg border bg-card px-3 py-1.5",
        )}
      >
        {s.bridge ? (
          <>
            <Tooltip>
              <TooltipTrigger asChild>
                <span
                  tabIndex={0}
                  className="inline-flex shrink-0 items-center gap-1 rounded text-emerald-500 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  <MessagesSquare className="size-4" aria-hidden />
                  <CircleCheck className="size-3.5" aria-hidden />
                  <span className="sr-only">Synced with Google Chat</span>
                </span>
              </TooltipTrigger>
              <TooltipContent side="bottom">Synced with Google Chat: {name}</TooltipContent>
            </Tooltip>
            <span className="min-w-0 flex-1 truncate font-medium">{name}</span>
            {problem && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    role="status"
                    tabIndex={0}
                    className="shrink-0 text-destructive focus-visible:outline-none"
                  >
                    <TriangleAlert className="size-4" aria-hidden />
                    <span className="sr-only">{s.bridge.last_error}</span>
                  </span>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="max-w-64">
                  {s.bridge.last_error}
                </TooltipContent>
              </Tooltip>
            )}
            {!s.connected && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Link
                    to={integrations}
                    aria-label="Connect Google Chat"
                    className="shrink-0 text-muted-foreground hover:text-foreground"
                  >
                    <Plug className="size-4" aria-hidden />
                  </Link>
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  Connect Google Chat to post as yourself
                </TooltipContent>
              </Tooltip>
            )}
            {s.can_manage && (
              <SyncMenu>
                <DropdownMenuItem onSelect={() => setImporting(true)}>
                  <Download className="size-4" aria-hidden /> Import messages
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setPicking(true)}>
                  <Repeat className="size-4" aria-hidden /> Change conversation
                </DropdownMenuItem>
                <DropdownMenuItem disabled={unlink.isPending} onSelect={stop}>
                  <Unlink className="size-4" aria-hidden /> Stop syncing
                </DropdownMenuItem>
              </SyncMenu>
            )}
          </>
        ) : (
          <>
            <MessagesSquare className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            <span className="min-w-0 flex-1 truncate text-muted-foreground">
              {compact ? "Google Chat" : "Keep this chat and a Google Chat conversation in step."}
            </span>
            <SyncMenu>
              <DropdownMenuItem onSelect={() => setPicking(true)}>
                <RefreshCw className="size-4" aria-hidden /> Sync with Google Chat
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setImporting(true)}>
                <Download className="size-4" aria-hidden /> Import messages
              </DropdownMenuItem>
            </SyncMenu>
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
    </TooltipProvider>
  );
}

/** The "..." that holds a chat's Google Chat actions, so the line above the chat stays one line. */
function SyncMenu({ children }: { children: ReactNode }) {
  return (
    <DropdownMenu>
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" aria-label="Google Chat options" className="shrink-0">
              <Ellipsis aria-hidden />
            </Button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent side="bottom">Google Chat options</TooltipContent>
      </Tooltip>
      <DropdownMenuContent align="end">{children}</DropdownMenuContent>
    </DropdownMenu>
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
    <TooltipProvider>
      <Dialog open onOpenChange={(open) => !open && onClose()}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">Sync with Google Chat</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            Messages sent from now on appear in both places. Pick a space, a group chat or a direct
            message; each can feed only one chat here. Members who connect Google Chat post there as
            themselves; everyone else is posted through your connection, with their name first.
            Google Chat works only with Google Workspace accounts.
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
                    placeholder={
                      spaces.isLoading ? "Loading conversations…" : "Pick a conversation"
                    }
                  />
                </SelectTrigger>
                <SelectContent>
                  {(spaces.data ?? []).map((sp) => (
                    <Tooltip key={sp.name}>
                      <TooltipTrigger asChild>
                        <SelectItem value={sp.name}>
                          {sp.display_name || sp.name}
                          <span className="ml-2 text-xs text-muted-foreground">
                            {KIND_LABEL[sp.kind]}
                          </span>
                        </SelectItem>
                      </TooltipTrigger>
                      <TooltipContent side="right" align="start" className="max-w-64">
                        <p className="mb-0.5 font-medium">Participants</p>
                        <p className="text-muted-foreground">
                          {(sp.members ?? []).length > 0
                            ? (sp.members ?? []).join(", ")
                            : sp.kind === "space"
                              ? "Open the space in Google Chat to see who is in it."
                              : "Google did not share the names."}
                        </p>
                      </TooltipContent>
                    </Tooltip>
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
    </TooltipProvider>
  );
}
