import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { ArrowDown, ListPlus, MessagesSquare, Plus, SmilePlus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { EmojiPicker } from "@/components/composer/EmojiPicker";
import { RichComposer } from "@/components/composer/RichComposer";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { LinkCards } from "@/components/shared/LinkCard";
import { UserAvatar } from "@/components/shared/UserAvatar";
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
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/hooks/auth";
import { useGoogleChat, useGoogleChatPeople } from "@/hooks/googleChat";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useMentionPeople } from "@/hooks/mentions";
import { CHAT_PAGE_SIZE, fetchOlderMessages, useChat } from "@/hooks/chat";
import { personName, type ChatMessage } from "@/lib/api-types";
import { openQuickCapture } from "@/lib/constants";
import { fullDate } from "@/lib/format";
import { formErrors } from "@/lib/forms";
import { parseGoogleLink } from "@/lib/googleLinks";
import { MessageText } from "@/lib/markdown";
import { cn } from "@/lib/utils";
import { GoogleChatSync } from "@/pages/GoogleChatSync";
import type { ProjectTabProps } from "@/pages/ProjectPage";

const GROUP_GAP_MS = 5 * 60 * 1000;
const PINNED_PX = 80; // this close to the bottom still counts as reading the latest messages

/** A message as a screen reader should hear it: mentions as "@Name", without the stored id. */
const spoken = (body: string) =>
  body
    .replace(/@\[([^\]\n]+)\]\((?:user:[0-9a-fA-F-]{36}|gchat:[0-9]{1,40})\)/g, "@$1")
    .replace(/[*_~`]/g, "")
    .slice(0, 40);

const dayLabel = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { dateStyle: "full" });
const clock = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { timeStyle: "short" });

/** Who wrote it, for grouping: a member's id, or the Google Chat sender's name (D316). */
const authorKey = (m: ChatMessage) => m.author?.id ?? `google:${m.external_author ?? ""}`;
/** The person to show: a member, or a stand-in for someone in Google Chat with no account here. */
const shownAuthor = (m: ChatMessage) =>
  // a member with no picture here wears their Google Chat one, where Google has one
  (m.author && !m.author.avatar_url && m.external_avatar
    ? { ...m.author, avatar_url: m.external_avatar }
    : m.author) ?? {
    id: authorKey(m),
    email: "",
    display_name: m.external_author || "Google Chat",
    avatar_url: m.external_avatar || null,
  };

/** A new group starts when the author changes, after a pause, or on a new day. */
function startsGroup(m: ChatMessage, prev: ChatMessage | undefined) {
  if (!prev || authorKey(prev) !== authorKey(m)) return true;
  const gap = new Date(m.created_at).getTime() - new Date(prev.created_at).getTime();
  return gap > GROUP_GAP_MS || dayLabel(prev.created_at) !== dayLabel(m.created_at);
}

/** Google links on a line of their own already show as a card inside the message. */
const standaloneGoogleLinks = (body: string) =>
  body
    .split("\n")
    .map((line) => parseGoogleLink(line)?.url)
    .filter((u): u is string => !!u);

/** Who reacted, as far as known: "Ada, Lee and 2 others". Google gives names for the people it
 * can name; the rest are only in the count. */
function reactorsText(r: { count: number; people?: string[] }) {
  const names = r.people ?? [];
  const shown = names.slice(0, 8);
  const more = r.count - shown.length;
  if (shown.length === 0) return `${r.count} ${r.count === 1 ? "person" : "people"}`;
  const list =
    shown.length > 1 ? `${shown.slice(0, -1).join(", ")} and ${shown.at(-1)}` : shown[0]!;
  return more > 0 ? `${shown.join(", ")} and ${more} ${more === 1 ? "other" : "others"}` : list;
}
const whoReacted = (r: { count: number; people?: string[] }) =>
  r.people?.length ? `: ${reactorsText(r)}` : "";

/** D321: the four quick reactions; the picker has the rest. */
export const QUICK_REACTIONS: [emoji: string, name: string][] = [
  ["\u{1F44D}", "thumbs up"],
  ["\u2764\uFE0F", "heart"],
  ["\u{1F60A}", "smile"],
  ["\u2753", "question"],
];
const ACTION_BUTTON =
  "rounded-md p-1 text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-accent hover:text-foreground focus-visible:opacity-100 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none data-[state=open]:opacity-100 [@media(hover:none)]:opacity-100 max-md:opacity-100 max-md:inline-flex max-md:size-10 max-md:items-center max-md:justify-center [@media(hover:none)]:inline-flex [@media(hover:none)]:size-10 [@media(hover:none)]:items-center [@media(hover:none)]:justify-center [&_svg]:size-4";

/** A message as a task title: plain text, mentions as names, first line, at most 200 characters. */
export const taskText = (body: string) =>
  body
    .replace(/@\[([^\]\n]+)\]\((?:user:[0-9a-fA-F-]{36}|gchat:[0-9]{1,40})\)/g, "$1")
    .replace(/[*_~`#]/g, "")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .join(" ")
    .slice(0, 200);

function MessageRow({
  message,
  mine,
  first,
  canDelete,
  onDelete,
  onReact,
}: {
  message: ChatMessage;
  mine: boolean;
  first: boolean;
  canDelete: boolean;
  onDelete: () => void;
  onReact: (emoji: string) => void;
}) {
  const author = shownAuthor(message);
  const name = personName(author);
  const fromGoogle = message.source === "google_chat";
  const [picking, setPicking] = useState(false);
  const reactions = message.reactions ?? [];
  return (
    <div
      className={cn(
        "group flex items-end gap-2 mt-0.5",
        first && "mt-3",
        mine && "flex-row-reverse",
      )}
    >
      {!mine &&
        (first ? <UserAvatar user={author} className="size-8" /> : <span className="w-8" />)}
      <div className={cn("flex max-w-[80%] min-w-0 flex-col", mine && "items-end")}>
        {first && (
          <p className="mb-1 flex items-baseline gap-2 px-1 text-xs">
            <span className="font-semibold">{mine ? "You" : name}</span>
            {fromGoogle && <span className="text-muted-foreground">via Google Chat</span>}
            <time
              dateTime={message.created_at}
              title={fullDate(message.created_at)}
              className="text-muted-foreground"
            >
              {clock(message.created_at)}
            </time>
          </p>
        )}
        <div
          className={cn(
            "rounded-2xl px-3 py-2",
            mine ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground",
          )}
        >
          <MessageText text={message.body} onPrimary={mine} />
        </div>
        <LinkCards text={message.body} skip={standaloneGoogleLinks(message.body)} />
        {reactions.length > 0 && (
          <ul aria-label="Reactions" className="mt-1 flex flex-wrap gap-1">
            {reactions.map((r) => (
              <li key={r.emoji}>
                <TooltipProvider delayDuration={100}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        aria-pressed={r.mine}
                        aria-label={`${r.emoji} ${r.count}${r.mine ? ", including you" : ""}${whoReacted(r)}. ${r.mine ? "Remove yours" : "Add yours"}`}
                        onClick={() => onReact(r.emoji)}
                        className={cn(
                          "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                          r.mine
                            ? "border-primary/50 bg-primary/10 text-foreground"
                            : "bg-card hover:bg-accent",
                        )}
                      >
                        <span aria-hidden>{r.emoji}</span>
                        <span aria-hidden className="tabular-nums">
                          {r.count}
                        </span>
                      </button>
                    </TooltipTrigger>
                    <TooltipContent className="max-w-64">
                      <span className="mr-1">{r.emoji}</span>
                      {reactorsText(r)}
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="relative flex items-center">
        <DropdownMenu>
          <DropdownMenuTrigger
            aria-label={`React or make a task: ${spoken(message.body)}`}
            className={ACTION_BUTTON}
          >
            <Plus aria-hidden />
          </DropdownMenuTrigger>
          <DropdownMenuContent align={mine ? "start" : "end"} className="w-56">
            <div role="group" aria-label="React" className="flex items-center gap-1 px-1 py-1">
              {QUICK_REACTIONS.map(([emoji, label]) => (
                <DropdownMenuItem
                  key={emoji}
                  aria-label={`React with ${label}`}
                  onSelect={() => onReact(emoji)}
                  className="size-9 justify-center p-0 text-lg"
                >
                  {emoji}
                </DropdownMenuItem>
              ))}
              <DropdownMenuItem
                aria-label="More reactions"
                onSelect={() => setPicking(true)}
                className="size-9 justify-center p-0"
              >
                <SmilePlus aria-hidden />
              </DropdownMenuItem>
            </div>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => openQuickCapture(taskText(message.body))}>
              <ListPlus aria-hidden /> Create task from message
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        {picking && (
          <EmojiPicker
            className={mine ? "left-auto right-0" : undefined}
            onClose={() => setPicking(false)}
            onPick={(emoji) => {
              setPicking(false);
              onReact(emoji);
            }}
          />
        )}
        {canDelete && (
          <button
            type="button"
            aria-label={`Delete message: ${spoken(message.body)}`}
            onClick={onDelete}
            className={cn(ACTION_BUTTON, "hover:text-destructive")}
          >
            <Trash2 aria-hidden />
          </button>
        )}
      </div>
    </div>
  );
}

/** Keyed by project, so a draft or scroll position never carries over to another project. */
export default function ChatTab({ labId, projectId, project }: ProjectTabProps) {
  const google = useGoogleChat(labId, projectId).status.data?.bridge; // D325
  return (
    <ChatPanel
      top={<GoogleChatSync labId={labId} projectId={projectId} compact />}
      alsoSentTo={google ? `the Google Chat ${google.space_name || "conversation"}` : undefined}
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
  alsoSentTo,
  top,
}: {
  labId: string;
  projectId?: string;
  canModerate: boolean;
  label: string;
  audience: string;
  /** Inside a side panel: fills it rather than sizing itself to the page. */
  inPanel?: boolean;
  /** Where messages also go (the lab chat's Google Chat space, D318), said under the composer. */
  alsoSentTo?: string;
  /** Above the messages: the project chat's Google Chat line (D325). */
  top?: ReactNode;
}) {
  const { email } = useAuth();
  const { messages, send, remove, react, markRead } = useChat(labId, projectId);
  const members = useMentionPeople(labId, projectId);
  // with a Google Chat conversation linked, people who are only there can be mentioned too
  const googlePeople = useGoogleChatPeople(labId, !!alsoSentTo, projectId).data;
  const people = useMemo(
    () => members && [...members, ...(googlePeople ?? [])],
    [members, googlePeople],
  );
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
        "relative flex scroll-mb-24 flex-col overflow-hidden rounded-lg border bg-card text-card-foreground",
        "md:scroll-mb-0",
        inPanel ? "h-full min-h-0" : "h-[calc(100dvh-5.5rem)] min-h-96 md:h-[calc(100dvh-13.5rem)]",
      )}
    >
      {top}
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
                const mine = !!m.author && m.author.email === email;
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
                      onReact={(emoji) =>
                        react.mutate(
                          { id: m.id, emoji },
                          {
                            // Older pages are not refetched by the poll, so update them here.
                            onSuccess: (updated) =>
                              setOlder((have) =>
                                have.map((o) => (o.id === updated.id ? updated : o)),
                              ),
                            onError: (e) =>
                              toast.error(formErrors(e, []).form ?? "Could not add that reaction."),
                          },
                        )
                      }
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
          className="absolute bottom-48 left-1/2 -translate-x-1/2 rounded-full"
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
        <RichComposer
          value={draft}
          onChange={setDraft}
          ariaLabel="Message"
          placeholder="Write a message"
          maxLength={4000}
          people={people}
          enterToSend
          submitLabel="Send"
          submitting={send.isPending}
          footer={
            <p className="text-xs text-muted-foreground">
              {alsoSentTo && <>Messages are also sent to {alsoSentTo}. </>}Do not share participant
              identifiers in chat. Press Enter to send, Shift+Enter for a new line.
            </p>
          }
        />
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
