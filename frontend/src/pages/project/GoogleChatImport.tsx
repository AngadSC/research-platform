import { useState } from "react";
import { Link } from "react-router";
import { MessagesSquare } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { RelativeTime } from "@/components/shared/RelativeTime";
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
import { useGoogleChat } from "@/hooks/googleChat";
import { api } from "@/lib/api";
import type { DocumentFull, GoogleChatSpace, GoogleChatThread } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";
import { cn } from "@/lib/utils";

/** D320: a Google Chat thread brought into the project as a document, read with your own Google
 * Chat connection. The button shows only when the site has Google Chat set up. */
export function GoogleChatImportButton({
  labId,
  projectId,
  onImported,
}: {
  labId: string;
  projectId: string;
  onImported: (doc: DocumentFull) => void;
}) {
  const [open, setOpen] = useState(false);
  const status = useGoogleChat(labId).status.data;
  if (!status?.configured) return null;
  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <MessagesSquare aria-hidden /> Import from Google Chat
      </Button>
      {open && (
        <ImportDialog
          labId={labId}
          projectId={projectId}
          connected={status.connected}
          onClose={() => setOpen(false)}
          onImported={(doc) => {
            setOpen(false);
            onImported(doc);
          }}
        />
      )}
    </>
  );
}

function ImportDialog({
  labId,
  projectId,
  connected,
  onClose,
  onImported,
}: {
  labId: string;
  projectId: string;
  connected: boolean;
  onClose: () => void;
  onImported: (doc: DocumentFull) => void;
}) {
  const qc = useQueryClient();
  const base = `/api/labs/${labId}/projects/${projectId}/google-chat`;
  const [space, setSpace] = useState("");
  const [thread, setThread] = useState("");
  const spaces = useQuery({
    queryKey: ["labs", labId, "google-chat", "project-spaces", projectId],
    queryFn: () => api<GoogleChatSpace[]>(`${base}/spaces/`),
    enabled: connected,
    retry: false,
  });
  const threads = useQuery({
    queryKey: ["labs", labId, "google-chat", "threads", projectId, space],
    queryFn: () => api<GoogleChatThread[]>(`${base}/threads/?space=${encodeURIComponent(space)}`),
    enabled: connected && !!space,
    retry: false,
  });
  const doImport = useMutation({
    mutationFn: () =>
      api<DocumentFull>(`${base}/import/`, { method: "POST", body: { space, thread } }),
    onSuccess: (doc) => {
      void qc.invalidateQueries({ queryKey: ["labs", labId, "projects", projectId] });
      toast.success("Thread imported as a document");
      onImported(doc);
    },
  });
  const error = spaces.error ?? threads.error ?? doImport.error;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogTitle className="text-base font-semibold">Import from Google Chat</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          Pick a space, then a thread. It becomes a document in this project with who said what and
          when. Do not import threads that identify participants.
        </DialogDescription>
        {!connected ? (
          <p className="text-sm">
            First{" "}
            <Link
              to={`/labs/${labId}/settings/integrations`}
              className="underline underline-offset-2"
            >
              connect Google Chat
            </Link>{" "}
            in Integrations.
          </p>
        ) : (
          <div className="grid gap-3">
            <div className="grid gap-2">
              <Label htmlFor="gchat-import-space">Space</Label>
              <Select
                value={space}
                onValueChange={(v) => {
                  setSpace(v);
                  setThread("");
                }}
                disabled={spaces.isLoading}
              >
                <SelectTrigger id="gchat-import-space">
                  <SelectValue
                    placeholder={spaces.isLoading ? "Loading spaces…" : "Pick a space"}
                  />
                </SelectTrigger>
                <SelectContent>
                  {(spaces.data ?? []).map((sp) => (
                    <SelectItem key={sp.name} value={sp.name}>
                      {sp.display_name || sp.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {space && (
              <fieldset className="grid gap-2">
                <legend className="mb-2 text-sm font-medium">Thread</legend>
                {threads.isLoading ? (
                  <p className="text-sm text-muted-foreground">Loading threads…</p>
                ) : (threads.data ?? []).length === 0 ? (
                  <p className="text-sm text-muted-foreground">No recent threads in this space.</p>
                ) : (
                  <ul className="grid max-h-72 gap-1 overflow-y-auto" role="radiogroup">
                    {threads.data!.map((t) => (
                      <li key={t.name}>
                        <button
                          type="button"
                          role="radio"
                          aria-checked={thread === t.name}
                          onClick={() => setThread(t.name)}
                          className={cn(
                            "w-full rounded-md border px-3 py-2 text-left text-sm hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                            thread === t.name && "border-primary bg-primary/5",
                          )}
                        >
                          <span className="line-clamp-2 block">{t.first || "(no text)"}</span>
                          <span className="block text-xs text-muted-foreground">
                            {t.count} message{t.count === 1 ? "" : "s"} · last{" "}
                            <RelativeTime value={t.last_at} />
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </fieldset>
            )}
          </div>
        )}
        {error && <FormError message={formErrors(error, []).form} />}
        <div className="flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button disabled={!thread || doImport.isPending} onClick={() => doImport.mutate()}>
            {doImport.isPending ? "Importing…" : "Import thread"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
