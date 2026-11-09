import { ChevronLeft, ChevronRight } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
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
import { useLab } from "@/hooks/workspace";
import type { CalendarItem } from "@/lib/api-types";
import { calendarHref, itemsOn, monthGrid } from "@/lib/calendar";
import { localDateISO } from "@/lib/format";
import { formErrors, type FormErrors } from "@/lib/forms";
import { projectColorStyle } from "@/lib/projectColors";
import { cn } from "@/lib/utils";
import { formValue } from "@/pages/admin/common";

const KIND: Record<CalendarItem["kind"], string> = {
  event: "Lab event",
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
  onOpenEvent,
}: {
  labId: string;
  item: CalendarItem;
  onOpenEvent: (item: CalendarItem) => void;
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
      <span className={cn("min-w-0 truncate", item.done && "text-muted-foreground line-through")}>
        {item.title}
      </span>
    </>
  );
  const className =
    "flex w-full items-start gap-1.5 rounded px-1 py-0.5 text-left text-xs hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none";
  return (
    <li style={item.project_color ? projectColorStyle(item.project_color) : undefined}>
      {href ? (
        <Link to={href} title={label} className={className}>
          {content}
        </Link>
      ) : (
        <button type="button" title={label} className={className} onClick={() => onOpenEvent(item)}>
          {content}
        </button>
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
              {(p) => <Input {...p} name="title" defaultValue={event?.title} />}
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
              {(p) => <Textarea {...p} name="notes" rows={3} defaultValue={event?.notes} />}
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
  const { list, create, update, remove } = useCalendar(
    labId,
    localDateISO(days[0]!),
    localDateISO(days[days.length - 1]!),
  );
  const [dialog, setDialog] = useState<{ event?: CalendarItem } | null>(null);
  const items = list.data ?? [];
  const today = localDateISO();
  const move = (months: number) =>
    setCursor((c) => new Date(c.getFullYear(), c.getMonth() + months, 1));

  return (
    <>
      <PageHeader
        title="Calendar"
        description={lab ? `Deadlines and events in ${lab.name}.` : undefined}
        actions={canEdit && <Button onClick={() => setDialog({})}>Add event</Button>}
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button variant="outline" size="icon" aria-label="Previous month" onClick={() => move(-1)}>
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
          const isToday = iso === today;
          const outside = d.getMonth() !== cursor.getMonth();
          return (
            <li
              key={iso}
              aria-current={isToday ? "date" : undefined}
              // Below sm the grid is a list of days with something on them, plus today.
              className={cn(
                "min-w-0 bg-card p-1.5 sm:min-h-24",
                onDay.length === 0 && !isToday && "hidden sm:block",
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
              {onDay.length > 0 && (
                <ul className="mt-1 grid min-w-0 grid-cols-[minmax(0,1fr)] gap-0.5">
                  {onDay.map((item) => (
                    <Entry
                      key={`${item.kind}:${item.id}`}
                      labId={labId}
                      item={item}
                      onOpenEvent={(event) => setDialog({ event })}
                    />
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ol>
      <EventDialog
        key={dialog?.event?.id ?? (dialog ? "new" : "closed")}
        event={dialog?.event}
        open={!!dialog}
        canEdit={canEdit}
        onClose={() => setDialog(null)}
        create={create}
        update={update}
        remove={remove}
      />
    </>
  );
}
