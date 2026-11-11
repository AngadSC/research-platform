import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { ArrowDown, MessagesSquare, Send, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { UserAvatar } from "@/components/shared/UserAvatar";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/hooks/auth";
import { CHAT_PAGE_SIZE, fetchOlderMessages, useChat } from "@/hooks/chat";
import { personName, type ChatMessage } from "@/lib/api-types";
import { fullDate } from "@/lib/format";
import { formErrors } from "@/lib/forms";
import { cn } from "@/lib/utils";
import type { ProjectTabProps } from "@/pages/ProjectPage";

const GROUP_GAP_MS = 5 * 60 * 1000;
const PINNED_PX = 80; // this close to the bottom still counts as reading the latest messages

const dayLabel = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { dateStyle: "full" });
const clock = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { timeStyle: "short" });

/** A new group starts when the author changes, after a pause, or on a new day. */
function startsGroup(m: ChatMessage, prev: ChatMessage | undefined) {
  if (!prev || prev.author.id !== m.author.id) return true;
  const gap = new Date(m.created_at).getTime() - new Date(prev.created_at).getTime();
  return gap > GROUP_GAP_MS || dayLabel(prev.created_at) !== dayLabel(m.created_at);
}

function MessageRow({
  message,
  mine,
  first,
  canDelete,
  onDelete,
}: {
  message: ChatMessage;
  mine: boolean;
  first: boolean;
  canDelete: boolean;
  onDelete: () => void;
}) {
  const name = personName(message.author);
  return (
    <div
      className={cn(
        "group flex items-end gap-2 mt-0.5",
        first && "mt-3",
        mine && "flex-row-reverse",
      )}
    >
      {!mine &&
        (first ? (
          <UserAvatar user={message.author} className="size-8" />
        ) : (
          <span className="w-8" />
        ))}
      <div className={cn("flex max-w-[80%] min-w-0 flex-col", mine && "items-end")}>
        {first && (
          <p className="mb-1 flex items-baseline gap-2 px-1 text-xs">
            <span className="font-semibold">{mine ? "You" : name}</span>
            <time
              dateTime={message.created_at}
              title={fullDate(message.created_at)}
              className="text-muted-foreground"
            >
              {clock(message.created_at)}
            </time>
          </p>
        )}
        <p
          className={cn(
            "rounded-2xl px-3 py-2 text-sm break-words whitespace-pre-wrap",
            mine ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground",
          )}
        >
          {message.body}
        </p>
      </div>
      {canDelete && (
        <button
          type="button"
          aria-label={`Delete message: ${message.body.slice(0, 40)}`}
          onClick={onDelete}
          className="rounded-md p-1 text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-accent hover:text-destructive focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none [@media(hover:none)]:opacity-100 [&_svg]:size-4"
        >
          <Trash2 aria-hidden />
        </button>
      )}
    </div>
  );
}

/** Keyed by project, so a draft or scroll position never carries over to another project. */
export default function ChatTab({ labId, projectId, project }: ProjectTabProps) {
  return (
    <ChatPanel
      key={projectId}
      labId={labId}
      projectId={projectId}
      canModerate={project.my_permissions.includes("edit_project")}
      label="Project chat"
      audience="this project"
      inPanel
    />
  );
}

/** One group chat: a project's, or with no `projectId` the whole lab's. */
export function ChatPanel({
  labId,
  projectId,
  canModerate,
  label,
  audience,
  inPanel,
}: {
  labId: string;
  projectId?: string;
  canModerate: boolean;
  label: string;
  audience: string;
  /** Inside a side panel: fills it rather than sizing itself to the page. */
  inPanel?: boolean;
}) {
  const { email } = useAuth();
  const { messages, send, remove, markRead } = useChat(labId, projectId);
  const [draft, setDraft] = useState("");
  const [older, setOlder] = useState<ChatMessage[]>([]);
  const [olderExhausted, setOlderExhausted] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [deleting, setDeleting] = useState<ChatMessage>();
  const [unseen, setUnseen] = useState(false);

  const panel = useRef<HTMLElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const heightBeforeOlder = useRef<number>(undefined);
  const lastId = useRef<string>(undefined);

  const latest = messages.data;
  const all = useMemo(() => [...older, ...(latest ?? [])], [older, latest]);
  const newest = all[all.length - 1]?.id;
  const newestAt = all[all.length - 1]?.created_at;
  const hasOlder = (latest?.length ?? 0) >= CHAT_PAGE_SIZE && !olderExhausted;

  const toBottom = () => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
    pinned.current = true;
    setUnseen(false);
  };

  // On a phone the headers above take most of the screen, so bring the whole panel into view.
  useLayoutEffect(() => {
    if (!inPanel) panel.current?.scrollIntoView?.({ block: "end" });
  }, [inPanel]);

  // Follow the conversation, unless the reader has scrolled up: then offer a jump instead.
  useLayoutEffect(() => {
    const isNew = newest !== undefined && newest !== lastId.current;
    const firstLoad = lastId.current === undefined;
    lastId.current = newest;
    if (!isNew) return;
    if (pinned.current || firstLoad) {
      const el = scroller.current;
      if (el) el.scrollTop = el.scrollHeight;
    } else {
      setUnseen(true);
    }
  }, [newest]);

  // D207: only what reached the screen counts as read. Scrolled up, new messages stay unread
  // until the reader comes back down, which clears `unseen` and runs this again.
  useEffect(() => {
    if (newestAt && pinned.current && !unseen) markRead(newestAt);
  }, [newestAt, unseen, markRead]);

  // Prepending older messages must not move what the reader is looking at.
  useLayoutEffect(() => {
    const el = scroller.current;
    if (el && heightBeforeOlder.current !== undefined) {
      el.scrollTop += el.scrollHeight - heightBeforeOlder.current;
      heightBeforeOlder.current = undefined;
    }
  }, [older]);

  const onScroll = () => {
    const el = scroller.current;
    if (!el) return;
    pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < PINNED_PX;
    if (pinned.current) setUnseen(false);
  };

  async function loadOlder() {
    const oldest = all[0];
    if (!oldest) return;
    setLoadingOlder(true);
    try {
      const page = await fetchOlderMessages(labId, projectId, oldest.created_at);
      heightBeforeOlder.current = scroller.current?.scrollHeight;
      setOlder((have) => [...page, ...have]);
      if (page.length < CHAT_PAGE_SIZE) setOlderExhausted(true);
    } catch (e) {
      toast.error(formErrors(e, []).form ?? "Could not load earlier messages.");
    } finally {
      setLoadingOlder(false);
    }
  }

  function submit() {
    const body = draft.trim();
    if (!body || send.isPending) return;
    send.mutate(body, {
      onSuccess: () => {
        setDraft("");
        pinned.current = true;
      },
      onError: (e) => toast.error(formErrors(e, ["body"]).form ?? "Your message was not sent."),
    });
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  }

  function confirmDelete() {
    if (!deleting) return;
    const id = deleting.id;
    remove.mutate(id, {
      onSuccess: () => {
        setOlder((have) => have.filter((m) => m.id !== id));
        toast.success("Message deleted");
      },
      onError: (e) => toast.error(formErrors(e, []).form ?? "Could not delete that message."),
      onSettled: () => setDeleting(undefined),
    });
  }

  return (
    <section
      ref={panel}
      aria-label={label}
      className={cn(
        "relative flex flex-col overflow-hidden rounded-lg border bg-card text-card-foreground",
        inPanel ? "h-full min-h-0" : "h-[calc(100dvh-5.5rem)] min-h-96 md:h-[calc(100dvh-13.5rem)]",
      )}
    >
      <div
        ref={scroller}
        onScroll={onScroll}
        role="log"
        aria-label="Messages"
        aria-live="polite"
        tabIndex={0}
        className="min-h-0 flex-1 overflow-y-auto p-4 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none focus-visible:ring-inset"
      >
        {messages.error && !latest ? (
          <FormError message={formErrors(messages.error, []).form} />
        ) : !latest ? (
          <div aria-busy="true" aria-label="Loading messages" className="grid gap-3">
            <Skeleton className="h-10 w-2/3" />
            <Skeleton className="h-10 w-1/2" />
          </div>
        ) : all.length === 0 ? (
          <EmptyState
            icon={MessagesSquare}
            title="No messages yet"
            description={`Say hello. Everyone in ${audience} can read and reply here.`}
            className="h-full border-0"
          />
        ) : (
          <>
            {hasOlder && (
              <div className="mb-2 text-center">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={loadingOlder}
                  onClick={() => void loadOlder()}
                >
                  Load earlier messages
                </Button>
              </div>
            )}
            <ol>
              {all.map((m, i) => {
                const prev = all[i - 1];
                const newDay = !prev || dayLabel(prev.created_at) !== dayLabel(m.created_at);
                const mine = m.author.email === email;
                return (
                  <li key={m.id}>
                    {newDay && (
                      <p className="my-3 flex items-center gap-3 text-xs font-semibold text-muted-foreground before:h-px before:flex-1 before:bg-border after:h-px after:flex-1 after:bg-border">
                        {dayLabel(m.created_at)}
                      </p>
                    )}
                    <MessageRow
                      message={m}
                      mine={mine}
                      first={startsGroup(m, prev)}
                      canDelete={mine || canModerate}
                      onDelete={() => setDeleting(m)}
                    />
                  </li>
                );
              })}
            </ol>
          </>
        )}
      </div>

      {unseen && (
        <Button
          size="sm"
          onClick={toBottom}
          className="absolute bottom-32 left-1/2 -translate-x-1/2 rounded-full"
        >
          <ArrowDown aria-hidden /> New messages
        </Button>
      )}

      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          submit();
        }}
        className="grid gap-2 border-t bg-muted p-3"
      >
        <Label htmlFor="chat-message" className="sr-only">
          Message
        </Label>
        <div className="flex items-end gap-2">
          <Textarea
            id="chat-message"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            maxLength={4000}
            rows={2}
            placeholder="Write a message"
            className="max-h-40 min-h-11 resize-none bg-card"
          />
          <Button type="submit" disabled={!draft.trim() || send.isPending}>
            <Send aria-hidden /> Send
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Do not share participant identifiers in chat. Press Enter to send, Shift+Enter for a new
          line.
        </p>
      </form>

      <Dialog open={!!deleting} onOpenChange={(open) => !open && setDeleting(undefined)}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">Delete this message?</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            It is removed for everyone and cannot be restored.
          </DialogDescription>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button variant="destructive" disabled={remove.isPending} onClick={confirmDelete}>
              Delete message
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}
