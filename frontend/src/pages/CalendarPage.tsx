import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useCalendar } from "@/hooks/admin";
import { googleOn, useGoogleEvents, useGoogleSync } from "@/hooks/meetings";
import { useLab } from "@/hooks/workspace";
import type { CalendarItem, GoogleEvent } from "@/lib/api-types";
import { calendarHref, itemsOn, monthGrid } from "@/lib/calendar";
import { localDateISO } from "@/lib/format";
import { formErrors, type FormErrors } from "@/lib/forms";
import { projectColorStyle } from "@/lib/projectColors";
import { cn } from "@/lib/utils";
import { formValue } from "@/pages/admin/common";
import { FeedDialog, GoogleCalendarDialog, MeetingDialog } from "@/pages/CalendarDialogs";

const KIND: Record<CalendarItem["kind"], string> = {
  event: "Lab event",
  meeting: "Meeting",
  deadline: "Deadline",
  task: "Task",
  inventory: "Inventory",
  ethics: "Ethics",
  funding: "Funding",
};
const KNOWN = ["title", "date", "end_date", "notes"];
const FIRST_OF_THIS_MONTH = () => {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), 1);
};

type Calendar = ReturnType<typeof useCalendar>;

function Entry({
  labId,
  item,
  onOpen,
}: {
  labId: string;
  item: CalendarItem;
  onOpen: (item: CalendarItem) => void;
}) {
  const href = calendarHref(labId, item);
  const label = [KIND[item.kind], item.project_name, item.title].filter(Boolean).join(": ");
  const content = (
    <>
      <span
        aria-hidden
        className={cn(
          "mt-1 size-2 shrink-0 rounded-full",
          item.project_color ? "bg-(--project)" : "bg-muted-foreground",
        )}
      />
      <span className="sr-only">{KIND[item.kind]}: </span>
      <span
        className={cn(
          "min-w-0 break-words line-clamp-2",
          item.done && "text-muted-foreground line-through",
        )}
      >
        {item.starts_at &&
          `${new Date(item.starts_at).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })} `}
        {item.title}
      </span>
    </>
  );
  const className = cn(
    "flex w-full items-start gap-1.5 rounded px-1 py-0.5 text-left text-xs hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
    // The project's colour as a tint and a bar, so each project is recognisable at a glance.
    item.project_color &&
      "border-l-[3px] border-(--project) bg-[color-mix(in_srgb,var(--project)_14%,transparent)]",
  );
  return (
    <li style={item.project_color ? projectColorStyle(item.project_color) : undefined}>
      {href ? (
        <Link to={href} title={label} className={className}>
          {content}
        </Link>
      ) : (
        <button type="button" title={label} className={className} onClick={() => onOpen(item)}>
          {content}
        </button>
      )}
    </li>
  );
}

const AGENDA_DAYS = 60;
const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });

/** Upcoming items by day: the full title is always visible, unlike the month cells. */
function Agenda({
  labId,
  items,
  google,
  start,
  loading,
  onOpen,
  onAdd,
}: {
  labId: string;
  items: CalendarItem[];
  google: GoogleEvent[];
  start: Date;
  loading: boolean;
  onOpen: (item: CalendarItem) => void;
  onAdd?: () => void;
}) {
  const groups = Array.from({ length: AGENDA_DAYS + 1 }, (_, i) => {
    const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i);
    const iso = localDateISO(d);
    const rows = itemsOn(items, iso).sort((a, b) =>
      (a.starts_at ?? "").localeCompare(b.starts_at ?? ""),
    );
    return { d, iso, rows, fromGoogle: googleOn(google, iso) };
  }).filter((g) => g.rows.length + g.fromGoogle.length > 0);
  if (groups.length === 0)
    return loading ? null : (
      <div className="rounded-lg border p-8 text-center">
        <p className="font-medium">Nothing coming up</p>
        <p className="mb-3 text-sm text-muted-foreground">
          Nothing is scheduled in the next {AGENDA_DAYS} days.
        </p>
        {onAdd && <Button onClick={onAdd}>Add event</Button>}
      </div>
    );
  return (
    <div aria-busy={loading || undefined} className="grid gap-4">
      {groups.map(({ d, iso, rows, fromGoogle }) => (
        <section key={iso} aria-labelledby={`agenda-${iso}`}>
          <h3 id={`agenda-${iso}`} className="mb-1 text-sm font-semibold">
            <time dateTime={iso}>
              {d.toLocaleDateString(undefined, {
                weekday: "long",
                month: "long",
                day: "numeric",
              })}
            </time>
          </h3>
          {fromGoogle.length > 0 && (
            <ul className="mb-1 grid gap-1">
              {fromGoogle.map((e) => (
                <GoogleEntry key={`google:${e.id}`} event={e} />
              ))}
            </ul>
          )}
          <ul className={cn("divide-y rounded-lg border", rows.length === 0 && "hidden")}>
            {rows.map((item) => {
              const href = calendarHref(labId, item);
              const row = (
                <>
                  <span className="w-20 shrink-0 text-muted-foreground">
                    {item.starts_at ? clock(item.starts_at) : "All day"}
                  </span>
                  <span className={cn("min-w-0 flex-1 break-words", item.done && "line-through")}>
                    {item.title}
                  </span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {[KIND[item.kind], item.project_name].filter(Boolean).join(" · ")}
                  </span>
                </>
              );
              const cls =
                "flex w-full items-baseline gap-3 px-3 py-2 text-left text-sm hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none";
              return (
                <li
                  key={`${item.kind}:${item.id}`}
                  style={item.project_color ? projectColorStyle(item.project_color) : undefined}
                  className={cn(item.project_color && "border-l-4 border-(--project)")}
                >
                  {href ? (
                    <Link to={href} className={cls}>
                      {row}
                    </Link>
                  ) : (
                    <button type="button" className={cls} onClick={() => onOpen(item)}>
                      {row}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}

/** One of your own Google events (D256): only you see it, and it opens in Google Calendar. */
function GoogleEntry({ event }: { event: GoogleEvent }) {
  const time = event.starts_at
    ? `${new Date(event.starts_at).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })} `
    : "";
  const content = (
    <>
      <CalendarDays aria-hidden className="mt-0.5 size-3 shrink-0 text-muted-foreground" />
      <span className="sr-only">Your Google Calendar: </span>
      <span className="min-w-0 break-words line-clamp-2 italic">
        {time}
        {event.title}
      </span>
    </>
  );
  const className =
    "flex w-full items-start gap-1.5 rounded border border-dashed px-1 py-0.5 text-left text-xs text-muted-foreground hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none";
  return (
    <li>
      {event.url || event.join_url ? (
        <a
          href={event.url || event.join_url}
          target="_blank"
          rel="noopener noreferrer"
          title={`Your Google Calendar: ${event.title}`}
          className={className}
        >
          {content}
        </a>
      ) : (
        <span title={`Your Google Calendar: ${event.title}`} className={className}>
          {content}
        </span>
      )}
    </li>
  );
}

function EventDialog({
  event,
  open,
  canEdit,
  onClose,
  create,
  update,
  remove,
}: {
  event: CalendarItem | undefined;
  open: boolean;
  canEdit: boolean;
  onClose: () => void;
  create: Calendar["create"];
  update: Calendar["update"];
  remove: Calendar["remove"];
}) {
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const v = (k: string) => formValue(fd, k);
    if (!v("title")) return setErrors({ fields: { title: "Enter a title" } });
    if (!v("date")) return setErrors({ fields: { date: "Pick a date" } });
    const body = {
      title: v("title"),
      date: v("date"),
      end_date: v("end_date") || null,
      notes: v("notes"),
    };
    try {
      if (event) await update.mutateAsync({ id: event.id, ...body });
      else await create.mutateAsync(body);
      toast.success(event ? "Event saved" : "Event added");
      onClose();
    } catch (err) {
      setErrors(formErrors(err, KNOWN));
    }
  }

  const f = errors.fields;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogTitle className="text-base font-semibold">
          {event ? event.title : "Add an event"}
        </DialogTitle>
        <DialogDescription className="sr-only">Lab calendar event</DialogDescription>
        <form onSubmit={submit} noValidate className="grid gap-3">
          <fieldset disabled={!canEdit} className="grid gap-3">
            <FormField label="Title" error={f.title}>
              {(p) => <Input maxLength={200} {...p} name="title" defaultValue={event?.title} />}
            </FormField>
            <div className="grid gap-3 sm:grid-cols-2">
              <FormField label="Date" error={f.date}>
                {(p) => (
                  <Input
                    {...p}
                    name="date"
                    type="date"
                    defaultValue={event?.date ?? localDateISO()}
                  />
                )}
              </FormField>
              <FormField label="End date (optional)" error={f.end_date}>
                {(p) => (
                  <Input {...p} name="end_date" type="date" defaultValue={event?.end_date ?? ""} />
                )}
              </FormField>
            </div>
            <FormField label="Notes" error={f.notes}>
              {(p) => (
                <Textarea
                  maxLength={5000}
                  {...p}
                  name="notes"
                  rows={3}
                  defaultValue={event?.notes}
                />
              )}
            </FormField>
          </fieldset>
          <FormError message={errors.form} />
          <div className="flex justify-end gap-2">
            {canEdit && event && (
              <Button
                type="button"
                variant="outline"
                className="mr-auto"
                disabled={remove.isPending}
                onClick={() =>
                  remove.mutate(event.id, {
                    onSuccess: () => {
                      toast.success("Event deleted");
                      onClose();
                    },
                    onError: () => toast.error("Could not delete the event."),
                  })
                }
              >
                Delete
              </Button>
            )}
            <DialogClose asChild>
              <Button type="button" variant="outline">
                {canEdit ? "Cancel" : "Close"}
              </Button>
            </DialogClose>
            {canEdit && <Button type="submit">Save</Button>}
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** The month grid: lab events plus everything dated that you may see. */
export function CalendarPage() {
  const { labId = "" } = useParams();
  const { data: lab } = useLab(labId);
  const canEdit = !!lab?.my_permissions.includes("contribute_lab");
  const [cursor, setCursor] = useState(FIRST_OF_THIS_MONTH);
  const days = useMemo(() => monthGrid(cursor.getFullYear(), cursor.getMonth()), [cursor]);
  const [params, setParams] = useSearchParams();
  // ?view= is "mine", "agenda" or "mine-agenda"; absent means the lab's month grid.
  const view = params.get("view") ?? "";
  const mine = view.startsWith("mine");
  const agenda = view.endsWith("agenda");
  const setView = (nextMine: boolean, nextAgenda: boolean) => {
    const v = [nextMine && "mine", nextAgenda && "agenda"].filter(Boolean).join("-");
    setParams(v ? { view: v } : {});
  };
  const now = new Date();
  const agendaEnd = new Date(now.getFullYear(), now.getMonth(), now.getDate() + AGENDA_DAYS);
  const { list, create, update, remove, meetings } = useCalendar(
    labId,
    agenda ? localDateISO(now) : localDateISO(days[0]!),
    agenda ? localDateISO(agendaEnd) : localDateISO(days[days.length - 1]!),
    mine,
  );
  const [dialog, setDialog] = useState<{ kind: "event" | "meeting"; item?: CalendarItem } | null>(
    null,
  );
  const [subscribing, setSubscribing] = useState(false);
  const [googleOpen, setGoogleOpen] = useState(false);
  const google = useGoogleSync(labId).status.data;
  const googleEvents =
    useGoogleEvents(
      labId,
      agenda ? localDateISO(now) : localDateISO(days[0]!),
      agenda ? localDateISO(agendaEnd) : localDateISO(days[days.length - 1]!),
      !!google?.connected && google.show_google_events,
    ).data ?? [];
  const items = list.data ?? [];
  const today = localDateISO();
  const move = (months: number) =>
    setCursor((c) => new Date(c.getFullYear(), c.getMonth() + months, 1));

  return (
    <>
      <PageHeader
        title="Calendar"
        description={
          mine
            ? "Your meetings, your tasks and the deadlines of your projects."
            : lab
              ? `Deadlines and events in ${lab.name}.`
              : undefined
        }
        actions={
          <>
            <Button variant="outline" onClick={() => setGoogleOpen(true)}>
              <CalendarDays aria-hidden /> Google Calendar
            </Button>
            <Button variant="outline" onClick={() => setSubscribing(true)}>
              Subscribe
            </Button>
            {canEdit && !mine && (
              <Button variant="outline" onClick={() => setDialog({ kind: "event" })}>
                Add event
              </Button>
            )}
            {canEdit && <Button onClick={() => setDialog({ kind: "meeting" })}>Add meeting</Button>}
          </>
        }
      />
      <div role="group" aria-label="Which calendar" className="mb-3 flex gap-1">
        <Button
          size="sm"
          variant={mine ? "outline" : "secondary"}
          aria-pressed={!mine}
          onClick={() => setView(false, agenda)}
        >
          Lab calendar
        </Button>
        <Button
          size="sm"
          variant={mine ? "secondary" : "outline"}
          aria-pressed={mine}
          onClick={() => setView(true, agenda)}
        >
          My calendar
        </Button>
        <span className="mx-1" />
        <Button
          size="sm"
          variant={agenda ? "outline" : "secondary"}
          aria-pressed={!agenda}
          onClick={() => setView(mine, false)}
        >
          Month
        </Button>
        <Button
          size="sm"
          variant={agenda ? "secondary" : "outline"}
          aria-pressed={agenda}
          onClick={() => setView(mine, true)}
        >
          Agenda
        </Button>
      </div>
      {agenda && list.error && <FormError message={formErrors(list.error, []).form} />}
      {agenda && (
        <Agenda
          labId={labId}
          items={items}
          google={googleEvents}
          start={now}
          loading={list.isLoading}
          onOpen={(open) =>
            setDialog({ kind: open.kind === "meeting" ? "meeting" : "event", item: open })
          }
          onAdd={canEdit && !mine ? () => setDialog({ kind: "event" }) : undefined}
        />
      )}
      {!agenda && (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              aria-label="Previous month"
              onClick={() => move(-1)}
            >
              <ChevronLeft aria-hidden />
            </Button>
            <Button variant="outline" onClick={() => setCursor(FIRST_OF_THIS_MONTH())}>
              Today
            </Button>
            <Button variant="outline" size="icon" aria-label="Next month" onClick={() => move(1)}>
              <ChevronRight aria-hidden />
            </Button>
            <h2 aria-live="polite" className="ml-2 text-base font-semibold">
              {cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" })}
            </h2>
          </div>
          {list.error && <FormError message={formErrors(list.error, []).form} />}
          <div className="hidden grid-cols-7 pb-1 text-center text-xs text-muted-foreground sm:grid">
            {days.slice(0, 7).map((d) => (
              <span key={d.getDay()}>{d.toLocaleDateString(undefined, { weekday: "short" })}</span>
            ))}
          </div>
          <ol
            aria-busy={list.isLoading || undefined}
            className="grid grid-cols-1 gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-7"
          >
            {days.map((d) => {
              const iso = localDateISO(d);
              const onDay = itemsOn(items, iso);
              const fromGoogle = googleOn(googleEvents, iso);
              const isToday = iso === today;
              const outside = d.getMonth() !== cursor.getMonth();
              return (
                <li
                  key={iso}
                  aria-current={isToday ? "date" : undefined}
                  // Below sm the grid is a list of days with something on them, plus today.
                  className={cn(
                    "min-w-0 bg-card p-1.5 sm:min-h-24",
                    onDay.length === 0 && fromGoogle.length === 0 && !isToday && "hidden sm:block",
                    outside && "sm:bg-muted",
                  )}
                >
                  <time
                    dateTime={iso}
                    className={cn(
                      "text-xs",
                      isToday
                        ? "rounded-full bg-primary px-1.5 py-0.5 font-semibold text-primary-foreground"
                        : "text-muted-foreground",
                    )}
                  >
                    <span className="sm:hidden">
                      {d.toLocaleDateString(undefined, {
                        weekday: "short",
                        month: "short",
                        day: "numeric",
                      })}
                    </span>
                    <span className="hidden sm:inline">{d.getDate()}</span>
                  </time>
                  {onDay.length + fromGoogle.length > 0 && (
                    <ul className="mt-1 grid min-w-0 grid-cols-[minmax(0,1fr)] gap-0.5">
                      {fromGoogle.map((e) => (
                        <GoogleEntry key={`google:${e.id}`} event={e} />
                      ))}
                      {onDay.map((item) => (
                        <Entry
                          key={`${item.kind}:${item.id}`}
                          labId={labId}
                          item={item}
                          onOpen={(open) =>
                            setDialog({
                              kind: open.kind === "meeting" ? "meeting" : "event",
                              item: open,
                            })
                          }
                        />
                      ))}
                    </ul>
                  )}
                </li>
              );
            })}
          </ol>
        </>
      )}
      <EventDialog
        key={dialog?.kind === "event" ? (dialog.item?.id ?? "new") : "closed"}
        event={dialog?.kind === "event" ? dialog.item : undefined}
        open={dialog?.kind === "event"}
        canEdit={canEdit}
        onClose={() => setDialog(null)}
        create={create}
        update={update}
        remove={remove}
      />
      {dialog?.kind === "meeting" && (
        <MeetingDialog
          labId={labId}
          meeting={dialog.item}
          canEdit={canEdit}
          onClose={() => setDialog(null)}
          actions={meetings}
        />
      )}
      {subscribing && <FeedDialog labId={labId} onClose={() => setSubscribing(false)} />}
      {googleOpen && <GoogleCalendarDialog labId={labId} onClose={() => setGoogleOpen(false)} />}
    </>
  );
}
