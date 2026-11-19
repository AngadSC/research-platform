import { Check, CircleHelp, ExternalLink, Video, X } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useMentionPeople } from "@/hooks/mentions";
import { useAnswerGoogleEvent, useAnswerMeeting } from "@/hooks/meetings";
import { useMe } from "@/hooks/workspace";
import type { CalendarItem, GoogleEvent } from "@/lib/api-types";
import { calendarHref } from "@/lib/calendar";
import { cn } from "@/lib/utils";

/**
 * Hover an event and its details open beside it: when, where, who else is on it and how they
 * answered, the call link, and your own Accept, Maybe and Decline. Clicking the event itself still
 * does what it did, and the same answers are in the meeting's own dialog, so nothing depends on
 * hovering. The card stays open while the pointer is on it.
 */
export function HoverCard({ trigger, children }: { trigger: ReactElement; children: ReactNode }) {
  return (
    <TooltipProvider delayDuration={350} skipDelayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>{trigger}</TooltipTrigger>
        <TooltipContent
          side="right"
          align="start"
          sideOffset={8}
          collisionPadding={12}
          className="w-80 max-w-[calc(100vw-2rem)] p-3 text-sm text-popover-foreground"
        >
          {children}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

const rule = <hr className="-mx-1 my-2 border-border" />;
const action =
  "inline-flex items-center gap-2 rounded-md border px-2 py-1 text-sm hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none";

const when = (iso: string) =>
  new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
const dayText = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

type Mark = "accepted" | "declined" | "maybe" | "none";
const MARKS: Record<Mark, { icon: typeof Check; label: string; tone: string }> = {
  accepted: { icon: Check, label: "Accepted", tone: "text-success-text" },
  declined: { icon: X, label: "Declined", tone: "text-danger-text" },
  maybe: { icon: CircleHelp, label: "Maybe", tone: "text-warning-text" },
  none: { icon: CircleHelp, label: "No reply yet", tone: "text-muted-foreground" },
};

function Person({ name, mark, note }: { name: string; mark: Mark; note?: string }) {
  const m = MARKS[mark];
  return (
    <li className="flex items-center gap-2 text-sm">
      <m.icon aria-hidden className={cn("size-3.5 shrink-0", m.tone)} />
      <span className="min-w-0 flex-1 truncate">
        {name}
        {note && <span className="text-xs text-muted-foreground"> ({note})</span>}
      </span>
      <span className="sr-only">{m.label}</span>
    </li>
  );
}

function People({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mt-3">
      <p className="mb-1 text-xs font-medium text-muted-foreground">{title}</p>
      <ul className="grid max-h-48 gap-1 overflow-y-auto">{children}</ul>
    </div>
  );
}

function Answers({
  mine,
  onAnswer,
  busy,
}: {
  mine: Mark;
  onAnswer: (status: "accepted" | "maybe" | "declined") => void;
  busy: boolean;
}) {
  return (
    <>
      {rule}
      <p className="mb-1 text-xs text-muted-foreground">
        Your answer: {MARKS[mine].label.toLowerCase()}
      </p>
      <div className="grid grid-cols-3 gap-1">
        {(["accepted", "maybe", "declined"] as const).map((s) => (
          <button
            key={s}
            type="button"
            disabled={busy}
            aria-pressed={mine === s}
            onClick={() => onAnswer(s)}
            className={cn(
              action,
              "justify-center disabled:opacity-50",
              mine === s && "border-primary/50 bg-primary/10 font-medium",
            )}
          >
            {s === "accepted" ? "Accept" : s === "maybe" ? "Maybe" : "Decline"}
          </button>
        ))}
      </div>
    </>
  );
}

const trim = (text: string, n = 220) => (text.length > n ? `${text.slice(0, n - 1)}…` : text);
const KIND: Record<CalendarItem["kind"], string> = {
  event: "Lab event",
  meeting: "Meeting",
  deadline: "Deadline",
  task: "Task",
  inventory: "Inventory",
  ethics: "Ethics",
  funding: "Funding",
};

/** The card for anything the app calendar holds: meetings, deadlines, tasks, lab dates. */
export function ItemCardBody({
  labId,
  item,
  onOpen,
}: {
  labId: string;
  item: CalendarItem;
  onOpen: (item: CalendarItem) => void;
}) {
  const meId = (useMe().data as { id?: string } | undefined)?.id;
  const people = useMentionPeople(labId);
  const answer = useAnswerMeeting(labId);
  const nameOf = (id: string) => people?.find((p) => p.id === id)?.name ?? "A lab member";
  const href = calendarHref(labId, item);
  const onIt = !!meId && item.attendees.includes(meId);
  const mine = ((item.responses ?? {})[meId ?? ""] as Mark | undefined) ?? "none";
  return (
    <div className="grid gap-0.5">
      <p className="text-xs text-muted-foreground">
        {[KIND[item.kind], item.project_name].filter(Boolean).join(" · ")}
      </p>
      <p className="text-base leading-snug font-semibold break-words">{item.title}</p>
      <p className="text-sm text-muted-foreground">
        {item.starts_at && item.ends_at
          ? `${dayText(item.date)}, ${when(item.starts_at)} to ${when(item.ends_at)}`
          : item.end_date
            ? `${dayText(item.date)} to ${dayText(item.end_date)}`
            : dayText(item.date)}
        {item.done && " · done"}
      </p>
      {item.notes && <p className="mt-2 text-sm break-words">{trim(item.notes)}</p>}
      {item.join_url && (
        <a
          href={item.join_url}
          target="_blank"
          rel="noopener noreferrer"
          className={cn(action, "mt-2 w-fit")}
        >
          <Video aria-hidden className="size-4" /> Join the call
        </a>
      )}
      {item.kind === "meeting" && item.attendees.length > 0 && (
        <People title={`On this meeting (${item.attendees.length + (item.guests?.length ?? 0)})`}>
          {item.attendees.map((id) => (
            <Person
              key={id}
              name={id === meId ? "You" : nameOf(id)}
              mark={((item.responses ?? {})[id] as Mark | undefined) ?? "none"}
            />
          ))}
          {(item.guests ?? []).map((email) => (
            <Person key={email} name={email} mark="none" note="invited by email" />
          ))}
        </People>
      )}
      {item.kind === "meeting" && onIt && (
        <Answers
          mine={mine}
          busy={answer.isPending}
          onAnswer={(status) =>
            answer.mutate(
              { id: item.id, status },
              { onError: () => toast.error("Could not save your answer.") },
            )
          }
        />
      )}
      {rule}
      {href ? (
        <Link to={href} className={cn(action, "w-fit")}>
          <ExternalLink aria-hidden className="size-4" /> Open
        </Link>
      ) : (
        <button type="button" onClick={() => onOpen(item)} className={cn(action, "w-fit")}>
          <ExternalLink aria-hidden className="size-4" /> Open details
        </button>
      )}
    </div>
  );
}

const GOOGLE_MARK: Record<string, Mark> = {
  accepted: "accepted",
  declined: "declined",
  tentative: "maybe",
  needsAction: "none",
};

/** The card for one of your own Google Calendar events. */
export function GoogleCardBody({ labId, event }: { labId: string; event: GoogleEvent }) {
  const answer = useAnswerGoogleEvent(labId);
  const invited = !!event.my_status;
  return (
    <div className="grid gap-0.5">
      <p className="text-xs text-muted-foreground">Your Google Calendar</p>
      <p className="text-base leading-snug font-semibold break-words">{event.title}</p>
      <p className="text-sm text-muted-foreground">
        {event.starts_at && event.ends_at
          ? `${dayText(event.date)}, ${when(event.starts_at)} to ${when(event.ends_at)}`
          : event.end_date
            ? `${dayText(event.date)} to ${dayText(event.end_date)}`
            : dayText(event.date)}
        {event.repeats && " · repeats"}
      </p>
      {event.location && <p className="text-sm break-words">{trim(event.location, 120)}</p>}
      {event.description && (
        <p className="mt-2 text-sm break-words whitespace-pre-line text-muted-foreground">
          {trim(event.description)}
        </p>
      )}
      {event.join_url && (
        <a
          href={event.join_url}
          target="_blank"
          rel="noopener noreferrer"
          className={cn(action, "mt-2 w-fit")}
        >
          <Video aria-hidden className="size-4" /> Join with Google Meet
        </a>
      )}
      {event.attendees.length > 0 && (
        <People title={`Invited (${event.attendees.length})`}>
          {event.attendees.map((a) => (
            <Person
              key={a.email}
              name={a.name || a.email}
              mark={GOOGLE_MARK[a.status] ?? "none"}
              note={a.organizer ? "organizer" : a.self ? "you" : undefined}
            />
          ))}
        </People>
      )}
      {invited && (
        <Answers
          mine={GOOGLE_MARK[event.my_status] ?? "none"}
          busy={answer.isPending}
          onAnswer={(status) =>
            answer.mutate(
              { id: event.id, status: status === "maybe" ? "tentative" : status },
              {
                onError: () =>
                  toast.error("Google did not take your answer. Reconnect Google Calendar?"),
              },
            )
          }
        />
      )}
      {event.url && (
        <>
          {rule}
          <a
            href={event.url}
            target="_blank"
            rel="noopener noreferrer"
            className={cn(action, "w-fit")}
          >
            <ExternalLink aria-hidden className="size-4" /> Open in Google Calendar
          </a>
        </>
      )}
    </div>
  );
}
