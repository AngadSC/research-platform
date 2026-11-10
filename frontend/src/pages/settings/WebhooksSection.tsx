import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useWebhookMutations, useWebhooks } from "@/hooks/integrations";
import type { Webhook, WebhookEvent } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";

const KIND_HELP: Record<string, string> = {
  webhook:
    "For Zapier, paste the address from a Webhooks by Zapier Catch Hook trigger. Zapier may need a paid plan for this. Make and your own server work too.",
  slack:
    "Paste the address of a Slack incoming webhook. Make one in your Slack workspace settings.",
};

const lastResult = (h: Webhook) => {
  if (!h.last_attempt_at) return "Nothing sent yet";
  if (h.last_status === null) return "Last message failed: no answer";
  return h.last_status >= 200 && h.last_status < 300
    ? "Last message delivered"
    : `Last message failed: error ${h.last_status}`;
};

/** PIs and lab admins: tell Zapier, Slack and similar tools when chosen things happen. Messages
 * say what happened and link here. They never include titles or names. */
export function WebhooksSection({ labId }: { labId: string }) {
  const list = useWebhooks(labId);
  const m = useWebhookMutations(labId);
  const [adding, setAdding] = useState(false);
  const [secret, setSecret] = useState("");
  const [removing, setRemoving] = useState<Webhook | null>(null);
  const events = list.data?.events ?? [];
  const hooks = list.data?.webhooks ?? [];

  const test = (h: Webhook) =>
    m.test.mutate(h.id, {
      onSuccess: (r) =>
        r.ok ? toast.success("Test message delivered") : toast.error("The test message failed."),
      onError: () => toast.error("The test message failed."),
    });

  return (
    <section aria-labelledby="automation" className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="automation" className="text-base font-semibold">
          Automation
        </h2>
        <Button variant="outline" onClick={() => setAdding(true)}>
          Add webhook
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        Send a message to Zapier, Slack or another service when something happens in this lab.
        Messages say what happened and link back here. They never include titles or people&apos;s
        names.
      </p>
      {hooks.length === 0 ? (
        <EmptyState title="No webhooks yet" description="Add one to get started." />
      ) : (
        <ul className="grid gap-2">
          {hooks.map((h) => (
            <li
              key={h.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-background px-4 py-3"
            >
              <div className="grid min-w-0">
                <span className="text-sm font-medium">{h.name}</span>
                <span className="truncate text-xs text-muted-foreground">
                  {h.host} · {h.events.length} {h.events.length === 1 ? "event" : "events"} ·{" "}
                  {lastResult(h)}
                  {h.last_attempt_at && (
                    <>
                      {" "}
                      <RelativeTime value={h.last_attempt_at} />
                    </>
                  )}
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => m.update.mutate({ id: h.id, is_active: !h.is_active })}
                >
                  {h.is_active ? "Turn off" : "Turn on"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={m.test.isPending}
                  onClick={() => test(h)}
                  aria-label={`Send a test message to ${h.name}`}
                >
                  Test
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setRemoving(h)}
                  aria-label={`Remove ${h.name}`}
                >
                  Remove
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {adding && (
        <AddDialog
          labId={labId}
          events={events}
          onClose={() => setAdding(false)}
          onCreated={setSecret}
        />
      )}
      <Dialog open={!!secret} onOpenChange={(o) => !o && setSecret("")}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">Copy this signing secret</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            It is shown only this once. Your server can use it to check that a message came from
            here, using the X-LabBench-Signature header. Zapier and Slack do not need it.
          </DialogDescription>
          <Input readOnly value={secret} aria-label="Signing secret" />
          <div className="flex justify-end">
            <DialogClose asChild>
              <Button>Done</Button>
            </DialogClose>
          </div>
        </DialogContent>
      </Dialog>
      <Dialog open={!!removing} onOpenChange={(o) => !o && setRemoving(null)}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">Remove {removing?.name}?</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            No more messages will be sent to it.
          </DialogDescription>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button
              variant="destructive"
              disabled={m.remove.isPending}
              onClick={() =>
                removing &&
                m.remove.mutate(removing.id, {
                  onSuccess: () => toast.success("Webhook removed"),
                  onSettled: () => setRemoving(null),
                })
              }
            >
              Remove
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}

function AddDialog({
  labId,
  events,
  onClose,
  onCreated,
}: {
  labId: string;
  events: WebhookEvent[];
  onClose: () => void;
  onCreated: (secret: string) => void;
}) {
  const { create } = useWebhookMutations(labId);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"webhook" | "slack">("webhook");
  const [url, setUrl] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [errors, setErrors] = useState<Record<string, string | undefined>>({});
  const [failure, setFailure] = useState<string>();

  const toggle = (value: string) =>
    setPicked((cur) => (cur.includes(value) ? cur.filter((x) => x !== value) : [...cur, value]));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !url.trim() || !picked.length) {
      setErrors({
        name: name.trim() ? undefined : "Enter a name.",
        url: url.trim() ? undefined : "Paste the address.",
        events: picked.length ? undefined : "Choose at least one event.",
      });
      return;
    }
    setFailure(undefined);
    create.mutate(
      { name: name.trim(), kind, url: url.trim(), events: picked },
      {
        onSuccess: (hook) => {
          toast.success("Webhook added");
          onClose();
          if (kind === "webhook") onCreated(hook.secret);
        },
        onError: (err) => {
          const r = formErrors(err, ["name", "kind", "url", "events"]);
          setErrors(r.fields);
          setFailure(r.form);
        },
      },
    );
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} noValidate className="grid gap-4">
          <DialogTitle className="text-base font-semibold">Add a webhook</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            The address is stored encrypted and is never shown again.
          </DialogDescription>
          <FormError message={failure} />
          <FormField label="Name" error={errors.name}>
            {(p) => <Input {...p} value={name} onChange={(e) => setName(e.target.value)} />}
          </FormField>
          <FormField label="Where to send it" hint={KIND_HELP[kind]}>
            {(p) => (
              <Select value={kind} onValueChange={(v) => setKind(v as "webhook" | "slack")}>
                <SelectTrigger {...p}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="webhook">Zapier or another webhook</SelectItem>
                  <SelectItem value="slack">Slack</SelectItem>
                </SelectContent>
              </Select>
            )}
          </FormField>
          <FormField label="Address" error={errors.url}>
            {(p) => (
              <Input
                {...p}
                type="password"
                autoComplete="off"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            )}
          </FormField>
          <fieldset className="grid gap-1">
            <legend className="text-sm font-medium">Send a message when</legend>
            {events.map((ev) => (
              <label key={ev.value} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={picked.includes(ev.value)}
                  onChange={() => toggle(ev.value)}
                />
                {ev.label}
              </label>
            ))}
            {errors.events && <p className="text-sm text-destructive">{errors.events}</p>}
          </fieldset>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              Add
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
