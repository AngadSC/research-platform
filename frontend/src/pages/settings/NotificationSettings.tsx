import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useMe } from "@/hooks/workspace";
import { api } from "@/lib/api";
import type { User } from "@/lib/api-types";
import { Section } from "@/pages/admin/common";

type Prefs = {
  digest?: "on" | "off";
  digest_hour?: string;
  quiet?: "on" | "off";
  quiet_start?: string;
  quiet_end?: string;
  delight?: "on" | "off";
};

const hourLabel = (h: number) => `${h % 12 === 0 ? 12 : h % 12}:00 ${h < 12 ? "am" : "pm"}`;
const HOURS = Array.from({ length: 24 }, (_, h) => ({ value: String(h), label: hourLabel(h) }));
const MORNING = HOURS.slice(5, 12);

function useSavePrefs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (preferences: Prefs) =>
      api<User>("/api/me/", { method: "PATCH", body: { preferences } }),
    onSuccess: (u) => qc.setQueryData(["me"], u),
    onError: () => toast.error("Could not save that setting."),
  });
}

function Toggle({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (on: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-3 text-sm">
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-1 size-4"
      />
      <span>
        <span className="font-medium">{label}</span>
        {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
      </span>
    </label>
  );
}

function HourSelect({
  label,
  value,
  options = HOURS,
  onChange,
  disabled,
}: {
  label: string;
  value: string;
  options?: { value: string; label: string }[];
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <label className="grid gap-1 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 rounded-md border bg-background px-2 disabled:opacity-50"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/** What reaches you, and when (D299): a morning digest instead of a stream, quiet hours for
 * email, and the small animations. Hours are in the time zone this browser is in. */
export function NotificationSettings() {
  const prefs = ((useMe().data as { preferences?: Prefs } | undefined)?.preferences ?? {}) as Prefs;
  const save = useSavePrefs();
  const digestOn = prefs.digest === "on";
  const quietOn = prefs.quiet === "on";
  return (
    <>
      <Section
        title="Your morning digest"
        description="One email each morning with what is due today and what is overdue, instead of a message for every change. Nothing is sent on a day with nothing due."
      >
        <Toggle
          label="Email me a daily digest"
          checked={digestOn}
          onChange={(on) => save.mutate({ digest: on ? "on" : "off" })}
        />
        <HourSelect
          label="Send it at"
          value={prefs.digest_hour ?? "8"}
          options={MORNING}
          disabled={!digestOn}
          onChange={(digest_hour) => save.mutate({ digest_hour })}
        />
      </Section>
      <Section
        title="Quiet hours"
        description="Email waits until quiet hours end. Notices still appear in the app straight away, so nothing is lost."
      >
        <Toggle
          label="Hold email during quiet hours"
          checked={quietOn}
          onChange={(on) => save.mutate({ quiet: on ? "on" : "off" })}
        />
        <div className="flex flex-wrap gap-4">
          <HourSelect
            label="From"
            value={prefs.quiet_start ?? "22"}
            disabled={!quietOn}
            onChange={(quiet_start) => save.mutate({ quiet_start })}
          />
          <HourSelect
            label="Until"
            value={prefs.quiet_end ?? "7"}
            disabled={!quietOn}
            onChange={(quiet_end) => save.mutate({ quiet_end })}
          />
        </div>
      </Section>
      <Section
        title="Little touches"
        description="A small animation when you finish a task. Always off if your device asks for less motion."
      >
        <Toggle
          label="Show small animations"
          checked={prefs.delight !== "off"}
          onChange={(on) => save.mutate({ delight: on ? "on" : "off" })}
        />
      </Section>
    </>
  );
}
