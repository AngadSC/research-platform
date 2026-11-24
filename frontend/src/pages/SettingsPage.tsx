import { useState } from "react";
import { useGlass } from "@/hooks/preferences";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { toast } from "sonner";
import { PageHeader } from "@/components/shared/PageHeader";
import { HashTabs } from "@/components/shared/TabNav";
import { useCurrentLabId } from "@/hooks/crumbs";
import { useLabs, useMe } from "@/hooks/workspace";
import { api } from "@/lib/api";
import type { User } from "@/lib/api-types";
import type { CustomTheme } from "@/lib/customTheme";
import { useTheme, type Theme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import { Section } from "@/pages/admin/common";
import { getDefaultDocsView, setDefaultDocsView, type DocsView } from "@/hooks/docsView";
import { IntegrationsPanel } from "@/pages/IntegrationsPage";
import { SecuritySections } from "@/pages/SecurityPage";
import { AiAccessSections, ConnectedAiApps } from "@/pages/settings/AiAccessSections";
import { AiKeysSection } from "@/pages/settings/AiKeysSection";
import { LabKeyNotice } from "@/pages/settings/LabAiKeySection";
import { LayoutSettings } from "@/pages/settings/LayoutSettings";
import { CustomThemes } from "@/pages/settings/CustomThemes";
import { NotificationSettings } from "@/pages/settings/NotificationSettings";
import { ProfileSection } from "@/pages/settings/ProfileSection";

type TaskView = "board" | "list";

/** Kinds that also send an email (D71, core/notifications.py EMAIL_KINDS). Read-only for now. */
export const EMAILED = [
  "Ethics approval expiring",
  "Retention review due",
  "Project exported",
  "Integration needs attention",
  "Training expiring or expired",
];
/** Only the PI and lab admins get this one. */
export const ADMIN_EMAILED = "Weekly training digest";
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
    <div
      role="radiogroup"
      aria-label={label}
      className="flex w-fit flex-wrap rounded-lg bg-muted p-0.5"
    >
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
  const me = useMe().data as
    (User & { preferences?: { task_view?: TaskView; custom_themes?: CustomTheme[] } }) | undefined;
  const setPref = useSetPreference();
  const [glass, setGlass] = useGlass();
  const [docsView, setDocsView] = useState<DocsView>(getDefaultDocsView);
  const labId = useCurrentLabId();
  const lab = useLabs().data?.find((l) => l.id === labId);
  const taskView = me?.preferences?.task_view ?? "board";
  const isAdmin = lab?.my_permissions.includes("manage_lab") ?? false;
  const customThemes = me?.preferences?.custom_themes ?? [];

  return (
    <>
      <PageHeader title="Settings" description="Your account and preferences." />
      <div className="max-w-2xl">
        <HashTabs
          label="Settings sections"
          tabs={[
            {
              id: "profile",
              label: "Profile",
              content: (
                <div className="grid gap-8">
                  <ProfileSection />
                  <Section
                    title="Integrations"
                    description="Connect storage, code and reference accounts."
                  >
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
                      description="Lab information, onboarding, links and AI."
                    >
                      <Link
                        className="text-sm font-medium underline-offset-4 hover:underline"
                        to={`/labs/${lab.id}/admin`}
                      >
                        Open Lab details
                      </Link>
                    </Section>
                  )}
                </div>
              ),
            },
            {
              id: "appearance",
              label: "Appearance",
              content: (
                <div className="grid gap-8">
                  <Section title="Appearance" description="Light, dark, or follow your device.">
                    <Choice<Theme>
                      label="Theme"
                      value={theme}
                      onChange={setTheme}
                      options={[
                        { value: "light", label: "Light" },
                        { value: "dark", label: "Dark" },
                        { value: "system", label: "System" },
                        ...customThemes.map((t) => ({
                          value: `custom:${t.id}` as Theme,
                          label: t.name,
                        })),
                      ]}
                    />
                  </Section>
                  <Section
                    title="Surfaces"
                    description="Glass adds a soft translucent look to menus and floating panels. Reduced glass uses solid surfaces, which is easier on older devices and for some eyes."
                  >
                    <Choice<"on" | "reduced">
                      label="Look"
                      value={glass}
                      onChange={setGlass}
                      options={[
                        { value: "on", label: "Glass" },
                        { value: "reduced", label: "Reduced glass" },
                      ]}
                    />
                  </Section>
                  <CustomThemes />
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
                    title="Documents and files"
                    description="How documents and files open by default. You can still switch on any page."
                  >
                    <Choice<DocsView>
                      label="Default documents view"
                      value={docsView}
                      onChange={(v) => {
                        setDocsView(v);
                        setDefaultDocsView(v);
                      }}
                      options={[
                        { value: "list", label: "List" },
                        { value: "grid", label: "Grid" },
                      ]}
                    />
                  </Section>
                </div>
              ),
            },
            { id: "layout", label: "Layout", content: <LayoutSettings /> },
            {
              id: "notifications",
              label: "Notifications",
              content: (
                <div className="grid gap-6">
                  <NotificationSettings />
                  <Section
                    title="Notifications"
                    description="Every notice appears in the app. These are also emailed."
                  >
                    <ul className="list-disc pl-5 text-sm" aria-label="Emailed notifications">
                      {(isAdmin ? [...EMAILED, ADMIN_EMAILED] : EMAILED).map((k) => (
                        <li key={k}>{k}</li>
                      ))}
                    </ul>
                    <p className="text-sm text-muted-foreground">
                      In the app only: {IN_APP_ONLY.join(", ")}.
                    </p>
                  </Section>
                </div>
              ),
            },
            {
              id: "security",
              label: "Security",
              content: (
                <div className="grid gap-4">
                  <h2 className="text-lg font-semibold">Security</h2>
                  <SecuritySections />
                </div>
              ),
            },
            ...(lab
              ? [
                  {
                    id: "integrations",
                    label: "Integrations",
                    content: (
                      <div className="grid gap-4">
                        <h2 className="text-lg font-semibold">Integrations</h2>
                        <IntegrationsPanel labId={lab.id} embedded />
                      </div>
                    ),
                  },
                ]
              : []),
            {
              id: "ai",
              label: "AI",
              content: (
                <div className="grid gap-8">
                  <LabKeyNotice />
                  <ConnectedAiApps />
                  <AiKeysSection />
                  <AiAccessSections />
                </div>
              ),
            },
          ]}
        />
      </div>
    </>
  );
}
