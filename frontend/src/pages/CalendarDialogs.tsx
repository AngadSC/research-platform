import { useState, type FormEvent } from "react";
import { Link } from "react-router";
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
import { useAnswerMeeting, useGoogleSync, useVideoOptions } from "@/hooks/meetings";
import { useReauth } from "@/hooks/reauth";
import { useLab, useMe, useMembers } from "@/hooks/workspace";
import { personName, type CalendarItem } from "@/lib/api-types";
import { toLocalInput } from "@/lib/calendar";
import { plural, whenZone } from "@/lib/format";
import { formErrors, type FormErrors } from "@/lib/forms";
import { formValue } from "@/pages/admin/common";

const KNOWN = [
  "title",
  "starts_at",
  "ends_at",
  "join_url",
  "notes",
  "attendees",
  "video",
  "guests",
];

const EMAIL = /^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$/;
/** The addresses typed in the guest box: separated by commas, spaces or new lines. */
const addressesIn = (text: string) => text.split(/[\s,;]+/).filter(Boolean);

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
                <span className="text-xs text-muted-foreground">
                  {CALL_NAME[call]} is not turned on for this site. Ask a site admin to turn it on.
                </span>
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
      {error?.includes("Integrations page") ? (
        <p role="alert" className="text-sm font-medium text-destructive">
          {error.replace(" on the Integrations page", "")} Open{" "}
          <Link className="underline" to={`/labs/${labId}/settings/integrations`}>
            Integrations
          </Link>{" "}
          and press Reconnect.
        </p>
      ) : (
        <FormError message={error} />
      )}
    </fieldset>
  );
}

const ANSWERS = [
  ["accepted", "Accept"],
  ["maybe", "Maybe"],
  ["declined", "Decline"],
] as const;

/** Your own answer to a meeting you are on, and how everyone has answered so far. */
function MyAnswer({
  labId,
  meeting,
  meId,
}: {
  labId: string;
  meeting: CalendarItem;
  meId: string;
}) {
  const answer = useAnswerMeeting(labId);
  const responses = (meeting.responses ?? {}) as Record<string, string>;
  const mine = responses[meId] ?? "";
  const count = (s: string) => Object.values(responses).filter((r) => r === s).length;
  return (
    <section aria-label="Your answer" className="grid gap-1.5 rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">Your answer</span>
        {ANSWERS.map(([status, label]) => (
          <Button
            key={status}
            type="button"
            size="sm"
            variant={mine === status ? "secondary" : "outline"}
            aria-pressed={mine === status}
            disabled={answer.isPending}
            onClick={() =>
              answer.mutate(
                { id: meeting.id, status },
                { onError: () => toast.error("Could not save your answer.") },
              )
            }
          >
            {label}
          </Button>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        {count("accepted")} accepted, {count("maybe")} maybe, {count("declined")} declined of{" "}
        {meeting.attendees.length + (meeting.guests?.length ?? 0)} invited.
      </p>
    </section>
  );
}

/** The next whole hour, and the hour after it: what a new meeting starts as. */
function nextHour() {
  const start = new Date();
  start.setHours(start.getHours() + 1, 0, 0, 0);
  return [start, new Date(start.getTime() + 3_600_000)] as const;
}

/** Add or change a meeting. Anyone who cannot change it sees it read only, Join button and all. */
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
  const isAdmin = !!useLab(labId).data?.my_permissions.includes("manage_lab");
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const [confirming, setConfirming] = useState(false);
  const [video, setVideo] = useState<Video>(meeting?.join_url ? "link" : "");
  const [people, setPeople] = useState<string[]>(meeting?.attendees ?? []);
  const everyone = members.map((m) => m.user.id);
  const wholeLab = everyone.length > 0 && everyone.every((id) => people.includes(id));
  const call = meeting?.video_provider as "" | "google_meet" | "zoom" | undefined;
  const callOwner = call ? members.find((m) => m.user.id === meeting?.call_owner)?.user : undefined;
  // D254: a call on someone else's account changes only through them.
  const lockedByCall = !!call && !!meeting?.call_owner && meeting.call_owner !== me?.id;
  // Only the organiser or a PI or lab admin may change a meeting; the others on it read it.
  const mayChange = !meeting || meeting.organiser === me?.id || isAdmin;
  const editable = canEdit && mayChange && !lockedByCall;
  const organiser = members.find((m) => m.user.id === meeting?.organiser)?.user;
  const nameOf = (id: string) => {
    const user = members.find((m) => m.user.id === id)?.user;
    return user ? personName(user) : null;
  };
  // guests are invited through a Meet call (Google emails them) or a Zoom call (labbenchos emails them),
  // new or already made
  const meetCall = video === "google_meet" || call === "google_meet";
  const zoomCall = video === "zoom" || call === "zoom";
  const [start, end] = nextHour();
  const { create, update, remove } = actions;

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const v = (k: string) => formValue(fd, k);
    if (!v("title")) return setErrors({ fields: { title: "Enter a title" } });
    if (!v("starts_at")) return setErrors({ fields: { starts_at: "Pick when it starts" } });
    if (!v("ends_at")) return setErrors({ fields: { ends_at: "Pick when it ends" } });
    const guests = addressesIn(v("guests"));
    const bad = guests.filter((g) => !EMAIL.test(g));
    if ((meetCall || zoomCall) && bad.length)
      return setErrors({
        fields: {
          guests: `This does not look like an email address: ${bad.slice(0, 3).join(", ")}`,
        },
      });
    const body = {
      title: v("title"),
      starts_at: new Date(v("starts_at")).toISOString(),
      ends_at: new Date(v("ends_at")).toISOString(),
      ...(call ? {} : { join_url: video === "link" ? v("join_url") : "" }),
      notes: v("notes"),
      attendees: people,
      ...(!meeting && (video === "google_meet" || video === "zoom") ? { video } : {}),
      ...(meetCall || zoomCall ? { guests } : {}),
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
          {meeting && !editable
            ? `Added by ${organiser ? personName(organiser) : "someone in the lab"}.${lockedByCall ? "" : " Only they or a lab admin can change it."}`
            : "A meeting with people and a time. For a lab date, like a deadline or holiday, use Add event in the three-dot menu on the lab calendar."}
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
        {meeting && me?.id && meeting.attendees.includes(me.id) && (
          <MyAnswer labId={labId} meeting={meeting} meId={me.id} />
        )}
        {meeting && !editable ? (
          <div className="grid gap-4">
            <dl className="grid gap-3 text-sm">
              <div className="grid gap-0.5">
                <dt className="text-xs text-muted-foreground">When</dt>
                <dd>
                  {meeting.starts_at && whenZone(meeting.starts_at)}
                  {meeting.ends_at && ` to ${whenZone(meeting.ends_at)}`}
                </dd>
              </div>
              <div className="grid gap-0.5">
                <dt className="text-xs text-muted-foreground">People on this meeting</dt>
                <dd>
                  {meeting.attendees.map(nameOf).filter(Boolean).join(", ") ||
                    plural(meeting.attendees.length, "person", "people")}
                </dd>
              </div>
              {meeting.notes && (
                <div className="grid gap-0.5">
                  <dt className="text-xs text-muted-foreground">Notes</dt>
                  <dd className="break-words whitespace-pre-wrap">{meeting.notes}</dd>
                </div>
              )}
            </dl>
            <div className="flex justify-end">
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  Close
                </Button>
              </DialogClose>
            </div>
          </div>
        ) : (
          <form onSubmit={submit} noValidate className="grid gap-3">
            <fieldset className="grid gap-3">
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
                      defaultValue={toLocalInput(
                        meeting?.ends_at ? new Date(meeting.ends_at) : end,
                      )}
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
                  hint="Paste a Zoom or Google Meet link (zoom.us, zoomgov.com or meet.google.com). It starts with https://"
                  error={f.join_url}
                >
                  {(p) => (
                    <Input
                      maxLength={500}
                      {...p}
                      name="join_url"
                      defaultValue={meeting?.join_url}
                    />
                  )}
                </FormField>
              )}
              <fieldset className="grid gap-1">
                <legend className="text-sm font-medium">People on this meeting</legend>
                <p className="text-xs text-muted-foreground">
                  Only the people on a meeting can see it. Whoever added it always stays on it.
                </p>
                <div className="grid max-h-72 gap-1 overflow-y-auto rounded-md border p-2">
                  {members.length > 1 && (
                    <div className="flex items-center gap-2 border-b pb-1 text-sm">
                      <input
                        id="meeting-whole-lab"
                        type="checkbox"
                        checked={wholeLab}
                        onChange={(e) => setPeople(e.target.checked ? everyone : [])}
                      />
                      <Label htmlFor="meeting-whole-lab">Whole lab</Label>
                    </div>
                  )}
                  {members.map((m) => {
                    const id = `meeting-person-${m.user.id}`;
                    return (
                      <div key={m.user.id} className="flex items-center gap-2 text-sm">
                        <input
                          id={id}
                          type="checkbox"
                          value={m.user.id}
                          checked={people.includes(m.user.id)}
                          onChange={(e) =>
                            setPeople((p) =>
                              e.target.checked
                                ? [...p, m.user.id]
                                : p.filter((x) => x !== m.user.id),
                            )
                          }
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
              {(meetCall || zoomCall) && (
                <FormField
                  label={
                    meetCall ? "Invite anyone with a Google account" : "Invite guests by email"
                  }
                  hint={
                    meetCall
                      ? "Type their email addresses, separated by commas. Google emails each one the invitation with the Meet link. Only you and the people above see this list."
                      : "Type their email addresses, separated by commas. Guests get an email from labbenchos with the join link. Only you and the people above see this list."
                  }
                  error={f.guests}
                >
                  {(p) => (
                    <Textarea
                      {...p}
                      name="guests"
                      rows={2}
                      placeholder="friend@gmail.com, colleague@university.edu"
                      defaultValue={(meeting?.guests ?? []).join(", ")}
                    />
                  )}
                </FormField>
              )}
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
                  onClick={() => setConfirming(true)}
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
        )}
        {meeting && (
          <Dialog open={confirming} onOpenChange={setConfirming}>
            <DialogContent>
              <DialogTitle className="text-base font-semibold">Delete {meeting.title}?</DialogTitle>
              <DialogDescription className="text-sm text-muted-foreground">
                The meeting will be removed from the lab calendar.
              </DialogDescription>
              <div className="flex justify-end gap-2">
                <DialogClose asChild>
                  <Button variant="outline">Cancel</Button>
                </DialogClose>
                <Button
                  variant="destructive"
                  disabled={remove.isPending}
                  onClick={() =>
                    remove.mutate(meeting.id, {
                      onSuccess: () => {
                        toast.success("Meeting deleted");
                        setConfirming(false);
                        onClose();
                      },
                      onError: () => toast.error("Could not delete the meeting."),
                    })
                  }
                >
                  Delete meeting
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        )}
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
