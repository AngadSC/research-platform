import { useEffect, useRef } from "react";
import { useIsFetching, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation } from "react-router";
import { toast } from "sonner";
import { PageHeader } from "@/components/shared/PageHeader";
import { useCurrentLabId } from "@/hooks/crumbs";
import { useLabs, useMe } from "@/hooks/workspace";
import { api } from "@/lib/api";
import type { User } from "@/lib/api-types";
import { useTheme, type Theme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import { Section } from "@/pages/admin/common";
import { NameSection, SecuritySections } from "@/pages/SecurityPage";
import { AiAccessSections } from "@/pages/settings/AiAccessSections";
import { AiKeysSection } from "@/pages/settings/AiKeysSection";

type TaskView = "board" | "list";

/** Kinds that also send an email (D71, core/notifications.py EMAIL_KINDS). Read-only for now. */
export const EMAILED = [
  "Ethics approval expiring",
  "Retention review due",
  "Project exported",
  "Integration needs attention",
  "Training expiring or expired",
  "Weekly training digest (PI and lab admins)",
];
export const IN_APP_ONLY = ["Task assigned", "Task unassigned", "Invitation accepted"];

function useSetPreference() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (preferences: { task_view: TaskView }) =>
      api<User>("/api/me/", { method: "PATCH", body: { preferences } }),
    onSuccess: (u) => qc.setQueryData(["me"], u),
    onError: () => toast.error("Could not save that setting."),
  });
}

function Choice<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex w-fit rounded-lg bg-muted p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-md px-3 py-1.5 text-sm text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
            value === o.value && "bg-background font-medium text-foreground shadow-sm",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const me = useMe().data as (User & { preferences?: { task_view?: TaskView } }) | undefined;
  const setPref = useSetPreference();
  const labId = useCurrentLabId();
  const lab = useLabs().data?.find((l) => l.id === labId);
  const taskView = me?.preferences?.task_view ?? "board";
  const isAdmin = lab?.my_permissions.includes("manage_lab") ?? false;
  const { hash, key } = useLocation();
  // Links to #profile, #security and #ai need scrolling by hand. The sections above load their
  // data after the first paint and push the target down, so scroll again once they have.
  const loading = useIsFetching() > 0;
  const settled = useRef("");
  useEffect(() => {
    if (!hash || settled.current === key) return;
    document.getElementById(hash.slice(1))?.scrollIntoView();
    if (!loading) settled.current = key;
  }, [hash, key, loading]);

  return (
    <>
      <PageHeader title="Settings" description="Your account and preferences." />
      <div className="grid max-w-2xl gap-8">
        <div id="profile">
          <NameSection />
        </div>
        <Section title="Appearance" description="Light, dark, or follow your device.">
          <Choice<Theme>
            label="Theme"
            value={theme}
            onChange={setTheme}
            options={[
              { value: "light", label: "Light" },
              { value: "dark", label: "Dark" },
              { value: "system", label: "System" },
            ]}
          />
        </Section>
        <Section title="Tasks" description="How project task lists open by default.">
          <Choice<TaskView>
            label="Default task view"
            value={taskView}
            onChange={(task_view) => setPref.mutate({ task_view })}
            options={[
              { value: "board", label: "Board" },
              { value: "list", label: "List" },
            ]}
          />
        </Section>
        <Section
          title="Notifications"
          description="Every notice appears in the app. These are also emailed."
        >
          <ul className="list-disc pl-5 text-sm" aria-label="Emailed notifications">
            {EMAILED.map((k) => (
              <li key={k}>{k}</li>
            ))}
          </ul>
          <p className="text-sm text-muted-foreground">
            In the app only: {IN_APP_ONLY.join(", ")}.
          </p>
        </Section>
        <div id="security" className="grid gap-4">
          <h2 className="text-lg font-semibold">Security</h2>
          <SecuritySections />
        </div>
        <div id="ai" className="grid gap-8">
          <AiKeysSection />
          <AiAccessSections />
        </div>
        <Section title="Integrations" description="Connect storage, code and reference accounts.">
          {lab ? (
            <Link
              className="text-sm font-medium underline-offset-4 hover:underline"
              to={`/labs/${lab.id}/settings/integrations`}
            >
              Open integrations
            </Link>
          ) : (
            <p className="text-sm text-muted-foreground">
              Join or create a lab to connect accounts.
            </p>
          )}
        </Section>
        {isAdmin && lab && (
          <Section
            title="Lab settings"
            description="Details, onboarding, inventory and admin tools."
          >
            <Link
              className="text-sm font-medium underline-offset-4 hover:underline"
              to={`/labs/${lab.id}/admin`}
            >
              Open Admin
            </Link>
          </Section>
        )}
      </div>
    </>
  );
}
