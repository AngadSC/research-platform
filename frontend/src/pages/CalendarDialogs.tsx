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
import { RelativeTime } from "@/components/shared/RelativeTime";
import { useCalendar, useCalendarFeed } from "@/hooks/admin";
import { ReauthCancelled } from "@/hooks/auth";
import { useConnect } from "@/hooks/integrations";
import { useGoogleSync, useVideoOptions } from "@/hooks/meetings";
import { useReauth } from "@/hooks/reauth";
import { useMe, useMembers } from "@/hooks/workspace";
import type { CalendarItem } from "@/lib/api-types";
import { toLocalInput } from "@/lib/calendar";
import { formErrors, type FormErrors } from "@/lib/forms";
import { formValue } from "@/pages/admin/common";

const KNOWN = ["title", "starts_at", "ends_at", "join_url", "notes", "attendees", "video"];

type Video = "" | "link" | "google_meet" | "zoom";
const CALL_NAME = { google_meet: "Google Meet", zoom: "Zoom" } as const;
const CONNECT_AS = { google_meet: "google_calendar", zoom: "zoom" } as const;

/** D254: how a new meeting gets its call. A choice needs your own account connected; until
 * then it offers to connect it (you come back to Settings, then add the meeting again). */
function VideoChoice({
  labId,
  value,
  onChange,
  error,
}: {
  labId: string;
  value: Video;
  onChange: (v: Video) => void;
  error?: string;
}) {
  const options = useVideoOptions(labId).data;
  const connect = useConnect(labId);
  const choices: [Video, string][] = [
    ["", "No video call"],
    ["link", "Paste a link"],
    ["google_meet", "Make a Google Meet call"],
    ["zoom", "Make a Zoom call"],
  ];
  return (
    <fieldset className="grid gap-1.5">
      <legend className="text-sm font-medium">Video call</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {choices.map(([v, label]) => {
          const id = `video-${v || "none"}`;
          const call = v === "google_meet" || v === "zoom" ? v : null;
          const setUp = !call || !!options?.[`${call}_available`];
          const connected = !call || !!options?.[call];
          return (
            <span key={id} className="flex items-center gap-2 text-sm">
              <input
                id={id}
                type="radio"
                name="video_choice"
                checked={value === v}
                disabled={!connected}
                onChange={() => onChange(v)}
              />
              <Label
                htmlFor={id}
                className={connected ? "font-normal" : "font-normal text-muted-foreground"}
              >
                {label}
              </Label>
              {call && !connected && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={!setUp || connect.isPending}
                  title={setUp ? undefined : "Not set up on this site yet"}
                  onClick={() => connect.mutate({ provider: CONNECT_AS[call] })}
                >
                  {call === "zoom" ? "Connect Zoom" : "Connect Google"}
                </Button>
              )}
              {call && !setUp && (
                <span className="text-xs text-muted-foreground">Not set up on this site yet</span>
              )}
            </span>
          );
        })}
      </div>
      {(value === "google_meet" || value === "zoom") && (
        <p className="text-xs text-muted-foreground">
          The call is made on your {CALL_NAME[value]} account when you save, and the join link fills
          in by itself. Only you will be able to change or delete this meeting.
          {value === "google_meet" &&
            " It also goes on your Google Calendar, with the people below as guests."}
        </p>
      )}
      <FormError message={error} />
    </fieldset>
  );
}

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
  const me = useMe().data;
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const [video, setVideo] = useState<Video>(meeting?.join_url ? "link" : "");
  const call = meeting?.video_provider as "" | "google_meet" | "zoom" | undefined;
  const callOwner = call ? members.find((m) => m.user.id === meeting?.call_owner)?.user : undefined;
  // D254: a call on someone else's account changes only through them.
  const lockedByCall = !!call && !!meeting?.call_owner && meeting.call_owner !== me?.id;
  const editable = canEdit && !lockedByCall;
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
      ...(call ? {} : { join_url: video === "link" ? v("join_url") : "" }),
      notes: v("notes"),
      attendees: fd.getAll("attendees").map(String),
      ...(!meeting && (video === "google_meet" || video === "zoom") ? { video } : {}),
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
        <DialogDescription className="text-sm text-muted-foreground">
          A meeting with people and a time. For a lab date, like a deadline or holiday, use Add
          event.
        </DialogDescription>
        {call && (
          <p className="text-sm text-muted-foreground">
            {CALL_NAME[call]} call on{" "}
            {callOwner ? callOwner.display_name || callOwner.email : "an organiser's"} account.
            {lockedByCall && " Only they can change or delete this meeting."}
          </p>
        )}
        {meeting?.join_url && (
          <Button asChild className="justify-self-start">
            <a href={meeting.join_url} target="_blank" rel="noreferrer noopener">
              Join meeting
            </a>
          </Button>
        )}
        <form onSubmit={submit} noValidate className="grid gap-3">
          <fieldset disabled={!editable} className="grid gap-3">
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
            {!call && (
              <VideoChoice
                labId={labId}
                value={meeting && video !== "link" && video !== "" ? "" : video}
                onChange={setVideo}
                error={f.video}
              />
            )}
            {!call && video === "link" && (
              <FormField
                label="Zoom or Google Meet link"
                hint="Paste the link from your invitation. It starts with https://"
                error={f.join_url}
              >
                {(p) => (
                  <Input maxLength={500} {...p} name="join_url" defaultValue={meeting?.join_url} />
                )}
              </FormField>
            )}
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
            {editable && meeting && (
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
                {editable ? "Cancel" : "Close"}
              </Button>
            </DialogClose>
            {editable && (
              <Button type="submit" disabled={create.isPending || update.isPending}>
                {!meeting && (video === "google_meet" || video === "zoom")
                  ? `Save and make the ${CALL_NAME[video]} call`
                  : "Save"}
              </Button>
            )}
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

/** D255, D256: your Google Calendar here. Connecting happens in Settings, through Google. */
export function GoogleCalendarDialog({ labId, onClose }: { labId: string; onClose: () => void }) {
  const { status, change, syncNow } = useGoogleSync(labId);
  const options = useVideoOptions(labId).data;
  const connect = useConnect(labId);
  const s = status.data;
  const toggle = (key: "show_google_events" | "push_meetings" | "push_tasks" | "push_deadlines") =>
    change.mutate(
      { [key]: !s?.[key] },
      { onError: (e) => toast.error(formErrors(e, []).form ?? "Not saved. Try again.") },
    );
  const rows: [typeof toggle extends (k: infer K) => void ? K : never, string, string][] = [
    [
      "show_google_events",
      "Show my Google events here",
      "Only you see them. Nothing from Google is stored.",
    ],
    ["push_meetings", "Put my meetings in Google", ""],
    ["push_tasks", "Put my tasks with due dates in Google", ""],
    ["push_deadlines", "Put my projects' deadlines in Google", ""],
  ];
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogTitle className="text-base font-semibold">Google Calendar</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          See your Google events on this calendar, and keep your meetings, tasks and deadlines in a
          calendar of their own in Google.
        </DialogDescription>
        {!s ? (
          <p aria-busy className="text-sm text-muted-foreground">
            Loading
          </p>
        ) : !s.connected ? (
          <div className="grid gap-3">
            <p className="text-sm">
              {options?.google_meet_available
                ? "Connect your own Google account. One sign-in covers Drive, Calendar and Meet; Google asks you to allow each."
                : "Google Calendar is not set up on this site yet. Ask whoever runs it to add the Google sign-in details."}
            </p>
            {options?.google_meet_available && (
              <Button
                className="justify-self-start"
                disabled={connect.isPending}
                onClick={() => connect.mutate({ provider: "google_calendar" })}
              >
                Connect Google
              </Button>
            )}
          </div>
        ) : (
          <div className="grid gap-4">
            <p className="text-sm">
              Connected as <span className="font-medium">{s.email || "your Google account"}</span>.
            </p>
            <ul className="grid gap-2">
              {rows.map(([key, label, hint]) => (
                <li key={key} className="flex items-start gap-2 text-sm">
                  <input
                    id={`gcal-${key}`}
                    type="checkbox"
                    className="mt-0.5"
                    checked={s[key]}
                    disabled={change.isPending}
                    onChange={() => toggle(key)}
                  />
                  <Label htmlFor={`gcal-${key}`} className="grid gap-0.5 font-normal">
                    {label}
                    {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
                  </Label>
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted-foreground">
              Items go to a separate calendar in Google, named after this lab, every 15 minutes.
              Only titles, times, project names and join links are sent, never notes.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <Button
                variant="outline"
                disabled={syncNow.isPending}
                onClick={() =>
                  syncNow.mutate(undefined, {
                    onSuccess: (r) =>
                      r.last_error
                        ? toast.error(r.last_error)
                        : toast.success(
                            `Synced: ${r.added} added, ${r.changed} changed, ${r.removed} removed`,
                          ),
                    onError: (e) => toast.error(formErrors(e, []).form ?? "Sync failed."),
                  })
                }
              >
                Sync now
              </Button>
              <span className="text-xs text-muted-foreground">
                {s.last_synced_at ? (
                  <>
                    Last synced <RelativeTime value={s.last_synced_at} />
                  </>
                ) : (
                  "Not synced yet"
                )}
              </span>
            </div>
            <FormError message={s.last_error || undefined} />
          </div>
        )}
        <div className="flex justify-end">
          <DialogClose asChild>
            <Button variant="outline">Close</Button>
          </DialogClose>
        </div>
      </DialogContent>
    </Dialog>
  );
}
