import { useState } from "react";
import { Link } from "react-router";
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
import { KIND_LABEL } from "@/hooks/googleChat";
import { api } from "@/lib/api";
import type { GoogleChatImportResult, GoogleChatSpace, GoogleChatThread } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";
import { cn } from "@/lib/utils";

const LATEST = "latest";

/** D327: a Google Chat thread, or a group chat's or direct message's latest messages, copied
 * into this chat (the lab chat, or `projectId`'s) as messages, read with your own Google Chat
 * connection. Each keeps its sender and time. Opened from the chat's Google Chat line. */
export function GoogleChatImportDialog({
  labId,
  projectId,
  connected,
  onClose,
}: {
  labId: string;
  projectId?: string;
  connected: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const base = projectId
    ? `/api/labs/${labId}/projects/${projectId}/chat/google`
    : `/api/labs/${labId}/chat/google`;
  const [space, setSpace] = useState("");
  const [thread, setThread] = useState("");
  const spaces = useQuery({
    queryKey: ["labs", labId, "google-chat", projectId ?? "lab", "spaces"],
    queryFn: () => api<GoogleChatSpace[]>(`${base}/spaces/`),
    enabled: connected,
    retry: false,
  });
  // D325: group chats and direct messages are one conversation, imported as their latest messages.
  const kind = spaces.data?.find((sp) => sp.name === space)?.kind;
  const threaded = kind === "space";
  const threads = useQuery({
    queryKey: ["labs", labId, "google-chat", projectId ?? "lab", "threads", space],
    queryFn: () => api<GoogleChatThread[]>(`${base}/threads/?space=${encodeURIComponent(space)}`),
    enabled: connected && !!space && threaded,
    retry: false,
  });
  const doImport = useMutation({
    mutationFn: () =>
      api<GoogleChatImportResult>(`${base}/import/`, {
        method: "POST",
        body: { space, thread: thread === LATEST ? "" : thread },
      }),
    onSuccess: ({ imported, skipped }) => {
      void qc.invalidateQueries({
        queryKey: projectId
          ? ["labs", labId, "projects", projectId, "messages"]
          : ["labs", labId, "chat", "messages"],
      });
      const plural = (n: number) => `${n} message${n === 1 ? "" : "s"}`;
      toast.success(
        imported
          ? `Imported ${plural(imported)}${skipped ? `; ${plural(skipped)} were already here` : ""}`
          : "Nothing new to import: those messages are already here",
      );
      onClose();
    },
  });
  const error = spaces.error ?? threads.error ?? doImport.error;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogTitle className="text-base font-semibold">Import from Google Chat</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          Pick a space, group chat or direct message, then a thread or its latest messages. They are
          added to this chat as messages, each under its sender and at the time it was sent, and are
          not sent back to Google.{" "}
          {projectId
            ? "Everyone who can see this project will see them, "
            : "Everyone in the lab will see them, "}
          including the names of people outside the lab who wrote them. Do not import conversations
          that identify participants.
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
              <Label htmlFor="gchat-import-space">Conversation</Label>
              <Select
                value={space}
                onValueChange={(v) => {
                  setSpace(v);
                  const picked = spaces.data?.find((sp) => sp.name === v);
                  setThread(picked && picked.kind !== "space" ? LATEST : "");
                }}
                disabled={spaces.isLoading}
              >
                <SelectTrigger id="gchat-import-space">
                  <SelectValue
                    placeholder={
                      spaces.isLoading ? "Loading conversations…" : "Pick a conversation"
                    }
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
            </div>
            {space && !threaded && (
              <p className="text-sm text-muted-foreground">
                Imports the latest messages of this {KIND_LABEL[kind ?? "group_chat"].toLowerCase()}{" "}
                (up to 1000).
              </p>
            )}
            {space && threaded && (
              <fieldset className="grid gap-2">
                <legend className="mb-2 text-sm font-medium">Thread</legend>
                {threads.isLoading ? (
                  <p className="text-sm text-muted-foreground">Loading threads…</p>
                ) : (
                  <ul className="grid max-h-72 gap-1 overflow-y-auto" role="radiogroup">
                    <li>
                      <button
                        type="button"
                        role="radio"
                        aria-checked={thread === LATEST}
                        onClick={() => setThread(LATEST)}
                        className={cn(
                          "w-full rounded-md border px-3 py-2 text-left text-sm hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                          thread === LATEST && "border-primary bg-primary/5",
                        )}
                      >
                        <span className="block font-medium">Latest messages</span>
                        <span className="block text-xs text-muted-foreground">
                          The whole space, up to 1000 messages
                        </span>
                      </button>
                    </li>
                    {(threads.data ?? []).map((t) => (
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
            {doImport.isPending ? "Importing…" : "Import"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
