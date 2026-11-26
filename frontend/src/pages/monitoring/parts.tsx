import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
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
import { Textarea } from "@/components/ui/textarea";
import { useInventory } from "@/hooks/admin";
import { useSensorMutations } from "@/hooks/monitoring";
import { useMembers } from "@/hooks/workspace";
import type { Sensor, SensorAlert, SensorInput } from "@/lib/api-types";
import { formErrors, type FormErrors } from "@/lib/forms";
import { cn } from "@/lib/utils";
import { formValue, NativeSelect } from "@/pages/admin/common";
import { showValue } from "./SensorChart";

export const UNITS = [
  { value: "c", label: "Temperature (°C)" },
  { value: "rh", label: "Humidity (%)" },
  { value: "co2", label: "CO2 (%)" },
] as const;

const STATUS: Record<Sensor["status"], { label: string; tone: string }> = {
  ok: { label: "OK", tone: "bg-success/15 text-success-text" },
  out_of_range: { label: "Out of range", tone: "bg-destructive/15 text-destructive" },
  silent: { label: "Silent", tone: "bg-warning/25 text-warning-text" },
  waiting: { label: "Waiting for a reading", tone: "bg-muted text-muted-foreground" },
  paused: { label: "Paused", tone: "bg-muted text-muted-foreground" },
};

export function StatusPill({ status }: { status: Sensor["status"] }) {
  const s = STATUS[status];
  return (
    <span
      className={cn("inline-flex rounded-full px-2 py-0.5 text-xs font-semibold", s.tone)}
      data-status={status}
    >
      {s.label}
    </span>
  );
}

/** On the inventory list: the linked sensor's reading and status, linking to its page. */
export function SensorBadge({ labId, sensor: s }: { labId: string; sensor: Sensor }) {
  const tone = STATUS[s.status].tone;
  return (
    <Link
      to={`/labs/${labId}/monitoring/${s.id}`}
      title={`${s.name}: ${STATUS[s.status].label}`}
      className={cn("rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums", tone)}
    >
      {s.last_value == null ? STATUS[s.status].label : showValue(s.last_value, s.unit_symbol)}
      {s.status !== "ok" && s.last_value != null && ` · ${STATUS[s.status].label}`}
    </Link>
  );
}

export const limitsText = (s: Sensor) =>
  s.low_limit != null && s.high_limit != null
    ? `${showValue(s.low_limit, s.unit_symbol)} to ${showValue(s.high_limit, s.unit_symbol)}`
    : s.high_limit != null
      ? `At most ${showValue(s.high_limit, s.unit_symbol)}`
      : s.low_limit != null
        ? `At least ${showValue(s.low_limit, s.unit_symbol)}`
        : "No limits set";

export const quietText = (minutes: number) =>
  minutes % 1440 === 0
    ? `${minutes / 1440} day${minutes === 1440 ? "" : "s"}`
    : minutes % 60 === 0
      ? `${minutes / 60} hour${minutes === 60 ? "" : "s"}`
      : `${minutes} minutes`;

/** What an alert is about, in a few words. */
export function alertText(s: Sensor, a: SensorAlert) {
  if (a.kind === "silent") return "No reading";
  const limit = a.kind === "high" ? s.high_limit : s.low_limit;
  return `${a.kind === "high" ? "Above" : "Below"} ${showValue(limit, s.unit_symbol)}, at worst ${showValue(a.peak, s.unit_symbol)}`;
}

/** The open (or not yet acknowledged) alert, with who is on it or a button to say you are. */
export function AlertBox({
  labId,
  sensor,
  alert,
  canEdit,
}: {
  labId: string;
  sensor: Sensor;
  alert: SensorAlert;
  canEdit: boolean;
}) {
  const [acking, setAcking] = useState(false);
  const open = alert.ended_at == null;
  return (
    <div
      className={cn(
        "grid gap-2 rounded-lg border p-3 text-sm",
        open ? "border-destructive/40 bg-destructive/5" : "bg-muted/40",
      )}
    >
      <p>
        <span className="font-medium">{alertText(sensor, alert)}</span>{" "}
        <span className="text-muted-foreground">
          {open ? "since " : "from "}
          <RelativeTime value={alert.started_at} />
          {!open && alert.ended_at && (
            <>
              , back to normal since{" "}
              {new Date(alert.ended_at).toLocaleTimeString(undefined, { timeStyle: "short" })}
            </>
          )}
        </span>
      </p>
      {alert.acknowledged_at ? (
        <p className="text-muted-foreground">
          {alert.acknowledged_by?.display_name || alert.acknowledged_by?.email} is on it
          {alert.note ? `: ${alert.note}` : "."}
        </p>
      ) : canEdit ? (
        <Button size="sm" className="justify-self-start" onClick={() => setAcking(true)}>
          Acknowledge
        </Button>
      ) : (
        <p className="text-muted-foreground">Nobody has acknowledged it yet.</p>
      )}
      {acking && (
        <AckDialog labId={labId} sensor={sensor} alert={alert} onClose={() => setAcking(false)} />
      )}
    </div>
  );
}

function AckDialog({
  labId,
  sensor,
  alert,
  onClose,
}: {
  labId: string;
  sensor: Sensor;
  alert: SensorAlert;
  onClose: () => void;
}) {
  const { acknowledge } = useSensorMutations(labId);
  const [error, setError] = useState<string>();
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const note = formValue(new FormData(e.currentTarget), "note");
    acknowledge.mutate(
      { id: alert.id, note },
      {
        onSuccess: () => {
          toast.success("Alert acknowledged");
          onClose();
        },
        onError: (err) => setError(formErrors(err, []).form ?? "Not saved. Try again."),
      },
    );
  }
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogTitle className="text-base font-semibold">Acknowledge the alert</DialogTitle>
        <DialogDescription>
          Tell the others you are on it: {sensor.name}, {alertText(sensor, alert).toLowerCase()}.
        </DialogDescription>
        <form onSubmit={submit} className="grid gap-3">
          <FormField label="What did you find or do?" hint="Optional. Kept with the alert.">
            {(p) => (
              <Textarea
                {...p}
                name="note"
                rows={3}
                maxLength={2000}
                placeholder="Door was ajar. Closed it and moved the enzyme stocks to Freezer A."
              />
            )}
          </FormField>
          <FormError message={error} />
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={acknowledge.isPending}>
              Acknowledge
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

const KNOWN = [
  "name",
  "item",
  "unit",
  "low_limit",
  "high_limit",
  "silent_after_minutes",
  "recipients",
  "active",
];

/** Add or change a sensor. Saving a new one opens its page, where the device is set up. */
export function SensorDialog({
  labId,
  sensor,
  onClose,
  onCreated,
}: {
  labId: string;
  sensor?: Sensor;
  onClose: () => void;
  onCreated?: (id: string) => void;
}) {
  const { create, update } = useSensorMutations(labId);
  const items = useInventory(labId, { category: "equipment" }).list.data ?? [];
  const members = useMembers(labId).data ?? [];
  const leads = members.filter((m) => m.role === "pi" || m.role === "lab_admin");
  const others = members.filter((m) => m.role !== "pi" && m.role !== "lab_admin");
  const [errors, setErrors] = useState<FormErrors>({ fields: {} });
  const f = errors.fields;

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const v = (k: string) => formValue(fd, k);
    const num = (k: string) => (v(k) === "" ? null : Number(v(k)));
    if (!v("name")) return setErrors({ fields: { name: "Enter a name" } });
    const recipients = fd.getAll("recipients").map(String);
    const body: SensorInput = {
      name: v("name"),
      item: v("item") || null,
      unit: v("unit") as SensorInput["unit"],
      low_limit: num("low_limit"),
      high_limit: num("high_limit"),
      silent_after_minutes: Number(v("silent_after_minutes") || 30),
      // nobody picked on a new sensor: the server adds the equipment's owner
      ...((sensor || recipients.length > 0) && { recipients }),
      ...(sensor && { active: fd.get("active") === "on" }),
    };
    try {
      if (sensor) await update.mutateAsync({ id: sensor.id, ...body });
      else onCreated?.((await create.mutateAsync(body)).id);
      toast.success(sensor ? "Sensor saved" : "Sensor added");
      onClose();
    } catch (err) {
      setErrors(formErrors(err, KNOWN));
    }
  }

  const picked = new Set(sensor?.recipients.map((u) => u.id) ?? []);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogTitle className="text-base font-semibold">
          {sensor ? "Sensor settings" : "Add a sensor"}
        </DialogTitle>
        <DialogDescription>
          {sensor
            ? "Limits, who is told, and how long it may stay quiet."
            : "Name it after what it watches. You set up the device on the next page."}
        </DialogDescription>
        <form onSubmit={submit} noValidate className="grid gap-3">
          <FormField label="Name" error={f.name}>
            {(p) => (
              <Input
                {...p}
                name="name"
                maxLength={200}
                defaultValue={sensor?.name}
                placeholder="-80 Freezer B"
              />
            )}
          </FormField>
          <FormField
            label="Equipment"
            hint="Its status shows on the inventory list."
            error={f.item}
          >
            {(p) => (
              <NativeSelect {...p} name="item" defaultValue={sensor?.item?.id ?? ""}>
                <option value="">Not linked</option>
                {items.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.name}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
          <div className="grid gap-3 sm:grid-cols-3">
            <FormField label="Measures" error={f.unit}>
              {(p) => (
                <NativeSelect {...p} name="unit" defaultValue={sensor?.unit ?? "c"}>
                  {UNITS.map((u) => (
                    <option key={u.value} value={u.value}>
                      {u.label}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
            <FormField label="Low limit" error={f.low_limit}>
              {(p) => (
                <Input
                  {...p}
                  name="low_limit"
                  type="number"
                  step="any"
                  defaultValue={sensor?.low_limit ?? ""}
                />
              )}
            </FormField>
            <FormField label="High limit" error={f.high_limit}>
              {(p) => (
                <Input
                  {...p}
                  name="high_limit"
                  type="number"
                  step="any"
                  defaultValue={sensor?.high_limit ?? ""}
                />
              )}
            </FormField>
          </div>
          <FormField
            label="Alert if silent for (minutes)"
            hint="A sensor that stops reporting may have lost power, and so may the freezer."
            error={f.silent_after_minutes}
          >
            {(p) => (
              <Input
                {...p}
                name="silent_after_minutes"
                type="number"
                min={5}
                max={10080}
                defaultValue={sensor?.silent_after_minutes ?? 30}
              />
            )}
          </FormField>
          <fieldset className="grid gap-1.5">
            <legend className="mb-1 text-sm font-medium">Who gets alerts</legend>
            <p className="text-xs text-muted-foreground">
              {leads.length
                ? `${leads.map((m) => m.user.display_name || m.user.email).join(", ")} (PIs and lab admins) always get them.`
                : "PIs and lab admins always get them."}{" "}
              {!sensor && "If you pick nobody, the equipment's owner is told too."}
            </p>
            {others.map((m) => (
              <label key={m.id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  name="recipients"
                  value={m.user.id}
                  defaultChecked={picked.has(m.user.id)}
                  className="size-4 accent-primary"
                />
                {m.user.display_name || m.user.email}
              </label>
            ))}
            {f.recipients && <p className="text-xs text-destructive">{f.recipients}</p>}
          </fieldset>
          {sensor && (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                name="active"
                defaultChecked={sensor.active}
                className="size-4 accent-primary"
              />
              Watching: send alerts (untick to pause, for a defrost or a move)
            </label>
          )}
          <FormError message={errors.form} />
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={create.isPending || update.isPending}>
              {sensor ? "Save" : "Add sensor"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
