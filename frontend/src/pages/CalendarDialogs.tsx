import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useCalendar, useCalendarFeed } from "@/hooks/admin";
import { ReauthCancelled } from "@/hooks/auth";
import { useReauth } from "@/hooks/reauth";
import { useMembers } from "@/hooks/workspace";
import type { CalendarItem } from "@/lib/api-types";
import { toLocalInput } from "@/lib/calendar";
import { formErrors, type FormErrors } from "@/lib/forms";
import { formValue } from "@/pages/admin/common";

const KNOWN = ["title", "starts_at", "ends_at", "join_url", "notes", "attendees"];

/** The next whole hour, and the hour after it: what a new meeting starts as. */
function nextHour() {
  const start = new Date();
  start.setHours(start.getHours() + 1, 0, 0, 0);
  return [start, new Date(start.getTime() + 3_600_000)] as const;
}

/** Add or change a meeting. The Join button stays usable for people who cannot edit. */
export function MeetingDialog({
  labId,
  meeting,
  canEdit,
  onClose,
  actions,
}: {
  labId: string;
  meeting: CalendarItem | undefined;
  canEdit: boolean;
  onClose: () => void;
  actions: ReturnType<typeof useCalendar>["meetings"];
}) {
  const members = useMembers(labId).data ?? [];
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const [start, end] = nextHour();
  const { create, update, remove } = actions;

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const v = (k: string) => formValue(fd, k);
    if (!v("title")) return setErrors({ fields: { title: "Enter a title" } });
    if (!v("starts_at")) return setErrors({ fields: { starts_at: "Pick when it starts" } });
    if (!v("ends_at")) return setErrors({ fields: { ends_at: "Pick when it ends" } });
    const body = {
      title: v("title"),
      starts_at: new Date(v("starts_at")).toISOString(),
      ends_at: new Date(v("ends_at")).toISOString(),
      join_url: v("join_url"),
      notes: v("notes"),
      attendees: fd.getAll("attendees").map(String),
    };
    try {
      if (meeting) await update.mutateAsync({ id: meeting.id, ...body });
      else await create.mutateAsync(body);
      toast.success(meeting ? "Meeting saved" : "Meeting added");
      onClose();
    } catch (err) {
      setErrors(formErrors(err, KNOWN));
    }
  }

  const f = errors.fields;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogTitle className="text-base font-semibold">
          {meeting ? meeting.title : "Add a meeting"}
        </DialogTitle>
        <DialogDescription className="sr-only">Calendar meeting</DialogDescription>
        {meeting?.join_url && (
          <Button asChild className="justify-self-start">
            <a href={meeting.join_url} target="_blank" rel="noreferrer noopener">
              Join meeting
            </a>
          </Button>
        )}
        <form onSubmit={submit} noValidate className="grid gap-3">
          <fieldset disabled={!canEdit} className="grid gap-3">
            <FormField label="Title" error={f.title}>
              {(p) => <Input maxLength={200} {...p} name="title" defaultValue={meeting?.title} />}
            </FormField>
            <div className="grid gap-3 sm:grid-cols-2">
              <FormField label="Starts" error={f.starts_at}>
                {(p) => (
                  <Input
                    {...p}
                    name="starts_at"
                    type="datetime-local"
                    defaultValue={toLocalInput(
                      meeting?.starts_at ? new Date(meeting.starts_at) : start,
                    )}
                  />
                )}
              </FormField>
              <FormField label="Ends" error={f.ends_at}>
                {(p) => (
                  <Input
                    {...p}
                    name="ends_at"
                    type="datetime-local"
                    defaultValue={toLocalInput(meeting?.ends_at ? new Date(meeting.ends_at) : end)}
                  />
                )}
              </FormField>
            </div>
            <FormField
              label="Zoom or Google Meet link (optional)"
              hint="Paste the link from your invitation. It starts with https://"
              error={f.join_url}
            >
              {(p) => (
                <Input maxLength={500} {...p} name="join_url" defaultValue={meeting?.join_url} />
              )}
            </FormField>
            <fieldset className="grid gap-1">
              <legend className="text-sm font-medium">People on this meeting</legend>
              <p className="text-xs text-muted-foreground">
                Only the people on a meeting can see it. Whoever added it always stays on it.
              </p>
              <div className="grid max-h-40 gap-1 overflow-y-auto rounded-md border p-2">
                {members.map((m) => {
                  const id = `meeting-person-${m.user.id}`;
                  return (
                    <div key={m.user.id} className="flex items-center gap-2 text-sm">
                      <input
                        id={id}
                        type="checkbox"
                        name="attendees"
                        value={m.user.id}
                        defaultChecked={meeting?.attendees.includes(m.user.id)}
                      />
                      <Label htmlFor={id} className="font-normal">
                        {m.user.display_name || m.user.email}
                      </Label>
                    </div>
                  );
                })}
              </div>
              <FormError message={f.attendees} />
            </fieldset>
            <FormField label="Notes" error={f.notes}>
              {(p) => (
                <Textarea
                  maxLength={5000}
                  {...p}
                  name="notes"
                  rows={3}
                  defaultValue={meeting?.notes}
                />
              )}
            </FormField>
          </fieldset>
          <FormError message={errors.form} />
          <div className="flex justify-end gap-2">
            {canEdit && meeting && (
              <Button
                type="button"
                variant="outline"
                className="mr-auto"
                disabled={remove.isPending}
                onClick={() =>
                  remove.mutate(meeting.id, {
                    onSuccess: () => {
                      toast.success("Meeting deleted");
                      onClose();
                    },
                    onError: () => toast.error("Could not delete the meeting."),
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

function CopyLink({ label, url }: { label: string; url: string }) {
  const copy = () =>
    navigator.clipboard?.writeText(url).then(
      () => toast.success("Link copied"),
      () => toast.error("Could not copy. Select it."),
    );
  return (
    <FormField label={label}>
      {(p) => (
        <div className="flex gap-2">
          <Input
            {...p}
            readOnly
            value={url}
            className="min-w-0"
            onFocus={(e) => e.target.select()}
          />
          <Button type="button" variant="outline" aria-label={`Copy ${label}`} onClick={copy}>
            Copy
          </Button>
        </div>
      )}
    </FormField>
  );
}

/** Make, replace or turn off your secret .ics link for this lab. */
export function FeedDialog({ labId, onClose }: { labId: string; onClose: () => void }) {
  const { status, issue, revoke } = useCalendarFeed(labId);
  const reauth = useReauth();
  const [token, setToken] = useState<string | null>(null);
  const active = status.data?.active ?? false;
  const link = (mine: boolean) =>
    `${window.location.origin}/api/calendar.ics?token=${token}${mine ? "&mine=1" : ""}`;

  const make = () =>
    reauth
      .run(() => issue.mutateAsync())
      .then(
        (r) => setToken(r.token),
        (err) => {
          if (!(err instanceof ReauthCancelled)) toast.error("Could not make the link.");
        },
      );
  const turnOff = () =>
    revoke.mutate(undefined, {
      onSuccess: () => {
        setToken(null);
        toast.success("Link turned off");
      },
      onError: () => toast.error("Could not turn the link off."),
    });

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogTitle className="text-base font-semibold">Add to Google Calendar</DialogTitle>
        <DialogDescription>
          A private link keeps your calendar app up to date with what you can see here. Your apps
          check the link a few times a day, so a change can take some hours to appear.
        </DialogDescription>
        {reauth.dialog}
        {token ? (
          <div className="grid gap-3">
            <CopyLink label="My calendar link" url={link(true)} />
            <CopyLink label="Lab calendar link" url={link(false)} />
            <p className="text-sm">
              In Google Calendar, open <strong>Other calendars</strong>, choose{" "}
              <strong>From URL</strong> and paste one of these links.
            </p>
            <p className="text-sm font-medium text-warning-text">
              These links are shown only now. Anyone who has one can read those dates, so keep it
              private, like a password.
            </p>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            {active
              ? "You have a link already. For safety it cannot be shown again. Making a new one stops the old one working."
              : "You do not have a link yet."}
          </p>
        )}
        <div className="flex flex-wrap justify-end gap-2">
          {active && (
            <Button
              type="button"
              variant="outline"
              className="mr-auto"
              disabled={revoke.isPending}
              onClick={turnOff}
            >
              Turn off link
            </Button>
          )}
          <DialogClose asChild>
            <Button type="button" variant="outline">
              Close
            </Button>
          </DialogClose>
          <Button type="button" disabled={issue.isPending} onClick={make}>
            {active || token ? "Make a new link" : "Make a link"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
