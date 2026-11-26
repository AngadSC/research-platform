import { useState, type FormEvent, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { ConfirmDelete } from "@/components/shared/ConfirmDelete";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormField } from "@/components/shared/FormField";
import { MoreMenu } from "@/components/shared/MoreMenu";
import { PageHeader } from "@/components/shared/PageHeader";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ReauthCancelled } from "@/hooks/auth";
import { useSensor, useSensorMutations } from "@/hooks/monitoring";
import { useReauth } from "@/hooks/reauth";
import { useLab } from "@/hooks/workspace";
import type { SensorDetail } from "@/lib/api-types";
import { when } from "@/lib/format";
import { formErrors } from "@/lib/forms";
import { Section } from "@/pages/admin/common";
import { AlertBox, alertText, limitsText, quietText, SensorDialog, StatusPill } from "./parts";
import { SensorChart, showValue } from "./SensorChart";

export function SensorPage() {
  const { labId = "", sensorId = "" } = useParams();
  const { data: lab } = useLab(labId);
  const { data: s, isPending, isError, dataUpdatedAt } = useSensor(labId, sensorId);
  const canEdit = !!lab?.my_permissions.includes("manage_inventory");
  const { remove } = useSensorMutations(labId);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const navigate = useNavigate();

  if (isError)
    return (
      <EmptyState
        title="Sensor not found"
        description="It may have been removed, or monitoring is turned off for this lab."
      />
    );
  if (isPending || !s)
    return (
      <div className="grid gap-3" aria-busy="true" aria-label="Loading">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );

  const people = ["PIs and lab admins", ...s.recipients.map((u) => u.display_name || u.email)];
  return (
    <>
      <PageHeader
        title={s.name}
        description={s.item ? `Watching ${s.item.name}.` : undefined}
        actions={
          canEdit ? (
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setEditing(true)}>
                Settings
              </Button>
              <MoreMenu
                label={`More for ${s.name}`}
                items={[{ label: "Delete sensor", onSelect: () => setDeleting(true) }]}
              />
            </div>
          ) : undefined
        }
      />
      <div className="grid gap-6">
        <section className="grid gap-3 rounded-xl border bg-card p-4" aria-label="Now">
          <div className="flex flex-wrap items-baseline gap-3">
            <span className="text-4xl font-semibold tabular-nums">
              {showValue(s.last_value, s.unit_symbol)}
            </span>
            <StatusPill status={s.status} />
            {s.last_at && (
              <span className="text-sm text-muted-foreground">
                Last reading <RelativeTime value={s.last_at} />
              </span>
            )}
          </div>
          <dl className="grid gap-1 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-muted-foreground">Allowed range</dt>
              <dd>{limitsText(s)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Alert if silent for</dt>
              <dd>{quietText(s.silent_after_minutes)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Who gets alerts</dt>
              <dd>{people.join(", ")}</dd>
            </div>
          </dl>
          {s.alert && <AlertBox labId={labId} sensor={s} alert={s.alert} canEdit={canEdit} />}
        </section>

        <Section
          title="Last 7 days"
          description="The line is the hourly average; the band, its lowest and highest."
          defaultOpen
        >
          <SensorChart
            points={s.series}
            low={s.low_limit}
            high={s.high_limit}
            symbol={s.unit_symbol}
            hours={24 * 7}
            end={dataUpdatedAt}
          />
        </Section>

        <Section title="Alerts" description="Every time it went out of range or quiet.">
          {s.history.length === 0 ? (
            <p className="text-sm text-muted-foreground">No alerts yet.</p>
          ) : (
            <ul className="grid gap-2 text-sm">
              {s.history.map((a) => (
                <li key={a.id} className="grid gap-0.5 rounded-lg border p-3">
                  <span className="font-medium">{alertText(s, a)}</span>
                  <span className="text-muted-foreground">
                    {when(a.started_at)}
                    {a.ended_at ? ` to ${when(a.ended_at)}` : ", still open"}
                  </span>
                  <span className="text-muted-foreground">
                    {a.acknowledged_at
                      ? `Acknowledged by ${a.acknowledged_by?.display_name || a.acknowledged_by?.email} at ${when(a.acknowledged_at)}${a.note ? `: ${a.note}` : ""}`
                      : "Not acknowledged"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Section>

        {canEdit && <SetupSection labId={labId} sensor={s} />}
      </div>
      {editing && <SensorDialog labId={labId} sensor={s} onClose={() => setEditing(false)} />}
      <ConfirmDelete
        open={deleting}
        name={s.name}
        noun="sensor"
        description="Its readings and alerts go too, and its device stops being heard."
        pending={remove.isPending}
        onConfirm={() =>
          remove.mutate(s.id, {
            onSuccess: () => {
              toast.success("Sensor deleted");
              navigate("..", { relative: "path" });
            },
            onError: () => toast.error("Could not delete the sensor."),
          })
        }
        onClose={() => setDeleting(false)}
      />
    </>
  );
}

const TOKEN_HINT = "<your token>";

/** The device's token (shown once), recipes for common devices and a test reading. */
function SetupSection({ labId, sensor: s }: { labId: string; sensor: SensorDetail }) {
  const { issueToken, revokeToken, testReading } = useSensorMutations(labId);
  const reauth = useReauth();
  const [token, setToken] = useState<string | null>(null);
  const [testError, setTestError] = useState<string>();
  const url = `${window.location.origin}/api/sensors/ingest/`;
  const t = token ?? TOKEN_HINT;
  const mid =
    s.low_limit != null && s.high_limit != null
      ? (s.low_limit + s.high_limit) / 2
      : (s.last_value ?? 4);

  const make = () =>
    reauth
      .run(() => issueToken.mutateAsync(s.id))
      .then(
        (r) => setToken(r.token),
        (err) => {
          if (!(err instanceof ReauthCancelled)) toast.error("Could not make a token.");
        },
      );
  const turnOff = () =>
    revokeToken.mutate(s.id, {
      onSuccess: () => {
        setToken(null);
        toast.success("Token turned off. The device can no longer send readings.");
      },
      onError: () => toast.error("Could not turn the token off."),
    });
  function test(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const value = Number(new FormData(e.currentTarget).get("value"));
    testReading.mutate(
      { id: s.id, value },
      {
        onSuccess: () => {
          setTestError(undefined);
          toast.success("Test reading saved");
        },
        onError: (err) => setTestError(formErrors(err, ["value"]).fields.value ?? "Not saved."),
      },
    );
  }

  return (
    <Section
      title="Set up the sensor"
      description="Give the device its token, then point it at this lab."
      defaultOpen={s.status === "waiting"}
    >
      {reauth.dialog}
      <div className="grid gap-2">
        <h3 className="text-sm font-semibold">1. The device's token</h3>
        {token ? (
          <>
            <CopyField label="Token" value={token} />
            <p className="text-sm font-medium text-warning-text">
              Shown only now. Anyone who has it can send readings for this sensor, so keep it
              private, like a password. It cannot read anything.
            </p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            {s.has_token
              ? `This sensor has a token, made ${when(s.token_created_at!)}. For safety it cannot be shown again. A new one stops the old one working.`
              : "The device sends readings with a secret token. Make one, then copy it to the device."}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={issueToken.isPending} onClick={make}>
            {s.has_token || token ? "Make a new token" : "Make a token"}
          </Button>
          {s.has_token && (
            <Button
              type="button"
              variant="outline"
              disabled={revokeToken.isPending}
              onClick={turnOff}
            >
              Turn off token
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-3">
        <h3 className="text-sm font-semibold">2. Point the device here</h3>
        <Recipe
          title="Shelly H&T (Gen2 or Plus)"
          intro={
            <>
              In the Shelly app or its web page, open <strong>Actions</strong>, add one for{" "}
              <strong>Temperature change</strong> (or <strong>Humidity change</strong>), and paste
              this address.
            </>
          }
          code={`${url}?token=${t}&value=\${ev.${s.unit === "rh" ? "rh" : "tC"}}`}
          note="This puts the token in the address, where router or proxy logs can keep it. Use it only for devices that cannot send a header, and turn the token off if the device is lost."
        />
        <Recipe
          title="ESP32 with a probe (Arduino)"
          intro={
            <>
              For a -80 °C freezer use a thermocouple board (MAX31855) or a PT100 board (MAX31865);
              a DS18B20 stops at -55 °C. This sends a reading once a minute.
            </>
          }
          code={esp32(url, t)}
        />
        <Recipe
          title="Any script (curl)"
          intro="Send a POST with the token in a header. Add an ISO time as at to send a reading taken earlier (up to a day)."
          code={`curl -X POST ${url} \\\n  -H "Authorization: Bearer ${t}" \\\n  -H "Content-Type: application/json" \\\n  -d '{"value": ${mid}}'`}
        />
      </div>

      <form onSubmit={test} className="grid gap-2">
        <h3 className="text-sm font-semibold">3. Check it works</h3>
        <p className="text-sm text-muted-foreground">
          Send a reading by hand. Outside the limits twice in a row, it alerts like a real one.
        </p>
        <div className="flex flex-wrap items-end gap-2">
          <div className="w-40">
            <FormField label={`Value (${s.unit_symbol})`} error={testError}>
              {(p) => <Input {...p} name="value" type="number" step="any" defaultValue={mid} />}
            </FormField>
          </div>
          <Button type="submit" variant="outline" disabled={testReading.isPending}>
            Send a test reading
          </Button>
        </div>
      </form>
    </Section>
  );
}

const esp32 = (url: string, token: string) => `#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Adafruit_MAX31855.h>

const char* WIFI = "your-wifi";
const char* PASS = "your-wifi-password";
const char* URL = "${url}";
const char* TOKEN = "${token}";

Adafruit_MAX31855 probe(18, 5, 19);  // CLK, CS, DO pins

void setup() {
  WiFi.begin(WIFI, PASS);
  probe.begin();
}

void loop() {
  double c = probe.readCelsius();
  if (WiFi.status() == WL_CONNECTED && !isnan(c)) {
    WiFiClientSecure client;
    client.setInsecure();  // or client.setCACert(...) to check the server too
    HTTPClient http;
    http.begin(client, URL);
    http.addHeader("Authorization", String("Bearer ") + TOKEN);
    http.addHeader("Content-Type", "application/json");
    http.POST(String("{\\"value\\":") + String(c, 2) + "}");
    http.end();
  }
  delay(60000);
}`;

function CopyField({ label, value }: { label: string; value: string }) {
  const copy = () =>
    navigator.clipboard?.writeText(value).then(
      () => toast.success("Copied"),
      () => toast.error("Could not copy. Select it."),
    );
  return (
    <FormField label={label}>
      {(p) => (
        <div className="flex gap-2">
          <Input
            {...p}
            readOnly
            value={value}
            className="min-w-0 font-mono"
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

function Recipe({
  title,
  intro,
  code,
  note,
}: {
  title: string;
  intro: ReactNode;
  code: string;
  note?: string;
}) {
  const copy = () =>
    navigator.clipboard?.writeText(code).then(
      () => toast.success("Copied"),
      () => toast.error("Could not copy. Select it."),
    );
  return (
    <div className="grid gap-2 rounded-lg border p-3">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-sm font-medium">{title}</h4>
        <Button
          type="button"
          size="sm"
          variant="outline"
          aria-label={`Copy ${title}`}
          onClick={copy}
        >
          Copy
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">{intro}</p>
      <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">
        <code>{code}</code>
      </pre>
      {note && <p className="text-xs text-warning-text">{note}</p>}
    </div>
  );
}
