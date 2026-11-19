import { Disclosure } from "@/components/shared/Disclosure";
import { Plug } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { ConnectDialog } from "@/components/shared/ConnectDialog";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { ProviderIcon } from "@/components/shared/ExternalLinkItem";
import { FormError } from "@/components/shared/FormError";
import { PageHeader } from "@/components/shared/PageHeader";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useAccounts, useConnect, useDisconnect, useProviders } from "@/hooks/integrations";
import { useAiGrants, useLabAiGrants } from "@/hooks/ai";
import { useLab } from "@/hooks/workspace";
import type { ConnectedAccount, IntegrationProvider } from "@/lib/api-types";
import { personName } from "@/lib/api-types";
import { useRegisterCommands } from "@/lib/commands";
import { formErrors } from "@/lib/forms";
import { CATEGORIES, connectError, needsReconnect, STATUS_HELP } from "@/lib/integrations";
import { ConnectClaude } from "@/pages/settings/AiAccessSections";
import { WebhooksSection } from "@/pages/settings/WebhooksSection";

interface Confirm {
  id: string;
  title: string;
  description: string;
  action: "Revoke" | "Disconnect";
  /** Your own Google Calendar is among what goes: offer to delete the labbenchos calendar. */
  calendar?: boolean;
}

/** Lab settings: connect outside services, see your connections, and (for PIs and lab admins)
 * everyone's, with a Revoke action. */
export function IntegrationsPage() {
  const { labId = "" } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const lab = useLab(labId).data;
  const providers = useProviders(labId);
  const canSeeAll = lab?.my_permissions.includes("manage_lab_integrations") ?? false;
  const everyone = useAccounts(labId, true, canSeeAll);
  const connect = useConnect(labId);
  const disconnect = useDisconnect(labId);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [deleteCalendar, setDeleteCalendar] = useState(false);
  const [initialError] = useState(() => params.get("error"));
  const [failure, setFailure] = useState<string>();
  const [keyed, setKeyed] = useState<IntegrationProvider | null>(null);

  // The server sends the browser back here with ?connected=<service> or ?error=<code>, plus
  // ?skipped=<services> when the person allowed only some of a shared sign-in's permissions.
  const connected = params.get("connected");
  const skipped = (params.get("skipped") ?? "").split(",").filter(Boolean);
  const errorCode = params.get("error");
  const label = (name: string) => providers.data?.find((p) => p.name === name)?.label ?? name;
  const loaded = !!providers.data;
  useEffect(() => {
    if (connected && loaded && skipped.length) {
      const group = providers.data?.find((p) => p.name === connected)?.bundle_label ?? "";
      const short = skipped.map((n) => label(n).replace(`${group} `, "")).join(", ");
      toast.warning(
        `${label(connected)} connected. ${skipped.map(label).join(", ")} ${skipped.length > 1 ? "were" : "was"} not, because you did not allow ${skipped.length > 1 ? "their permissions" : "its permission"}.`,
        { description: `To add it later, choose Add ${short} on the ${group} card.` },
      );
    } else if (connected && loaded) toast.success(`${label(connected)} connected`);
    if (errorCode || (connected && loaded)) setParams({}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected, errorCode, loaded]);

  const commands = useMemo(
    () => [
      {
        id: "integrations:open",
        label: "Go to Integrations",
        group: "Lab",
        onSelect: () => void navigate(`/labs/${labId}/settings/integrations`),
      },
    ],
    [navigate, labId],
  );
  useRegisterCommands(commands);

  const start = (p: IntegrationProvider) => {
    setFailure("");
    connect.mutate(
      { provider: p.name },
      { onError: (e) => setFailure(formErrors(e, ["code"]).form) },
    );
  };
  const run = () => {
    if (!confirm) return;
    const deleteAppCalendar = !!confirm.calendar && deleteCalendar;
    disconnect.mutate(
      { id: confirm.id, deleteAppCalendar },
      {
        onSuccess: () =>
          toast.success(confirm.action === "Revoke" ? "Connection revoked" : "Disconnected"),
        onError: (e) => toast.error(formErrors(e, []).form ?? "Something went wrong."),
        onSettled: () => setConfirm(null),
      },
    );
  };

  const cols: Column<ConnectedAccount>[] = [
    { key: "who", header: "Member", cell: (a) => personName(a.user) },
    { key: "svc", header: "Service", cell: (a) => label(a.provider) },
    { key: "acct", header: "Account", cell: (a) => a.external_email || "Not shown" },
    { key: "status", header: "Status", cell: (a) => <StatusBadge status={a.status} /> },
    {
      key: "used",
      header: "Last used",
      cell: (a) => (a.last_used_at ? <RelativeTime value={a.last_used_at} /> : "Never"),
    },
    {
      key: "act",
      header: "Actions",
      className: "text-right",
      cell: (a) =>
        a.status === "revoked" ? null : (
          <Button
            variant="outline"
            size="sm"
            aria-label={`Revoke ${personName(a.user)}'s ${label(a.provider)} connection`}
            onClick={() =>
              setConfirm({
                id: a.id,
                action: "Revoke",
                title: `Revoke ${personName(a.user)}'s connection?`,
                description: `They will need to connect ${label(a.provider)} again. Items they linked stay in place.`,
              })
            }
          >
            Revoke
          </Button>
        ),
    },
  ];

  return (
    <div className="grid gap-8">
      <PageHeader
        title="Integrations"
        description="Connect AI apps like Claude, and outside services you use with your projects. Each service below says what connecting it lets labbenchos do."
      />
      <p className="text-sm text-muted-foreground">Each person connects their own accounts here.</p>
      <FormError message={failure ?? connectError(initialError)} />
      <AiAppsSection />
      <Disclosure card region defaultOpen title="Services">
        <div className="grid gap-3">
          {providers.isLoading ? (
            <div aria-busy="true" aria-label="Loading" className="grid gap-2">
              <Skeleton className="h-16 w-full" />
            </div>
          ) : providers.data?.length ? (
            groupByCategory(providers.data).map(([cat, label, list]) => (
              <div key={cat} className="grid gap-2">
                <h3 className="text-sm font-medium text-muted-foreground">{label}</h3>
                <ul className="grid gap-3 sm:grid-cols-2">
                  {list.map((members) => {
                    const p = members[0]!;
                    const onConnect = () => (p.auth_type === "api_key" ? setKeyed(p) : start(p));
                    const disconnectWith = (
                      id: string,
                      title: string,
                      extra: string,
                      calendar = false,
                    ) => {
                      setDeleteCalendar(false);
                      setConfirm({
                        id,
                        action: "Disconnect",
                        title,
                        calendar,
                        description: `${extra}Linked items stay in your projects, but we stop checking them until you connect again.`,
                      });
                    };
                    return members.length > 1 ? (
                      <BundleCard
                        key={p.name}
                        members={members}
                        busy={connect.isPending}
                        onConnect={onConnect}
                        onDisconnect={(id, what, calendar) =>
                          disconnectWith(
                            id,
                            `Disconnect ${p.bundle_label}?`,
                            what.includes(", ")
                              ? `This disconnects ${what} together, because they use one sign-in. `
                              : `This disconnects ${what}. `,
                            calendar,
                          )
                        }
                      />
                    ) : (
                      <ProviderCard
                        key={p.name}
                        p={p}
                        busy={connect.isPending}
                        onConnect={onConnect}
                        onDisconnect={() =>
                          p.account &&
                          disconnectWith(
                            p.account.id,
                            `Disconnect ${p.label}?`,
                            "",
                            p.name === "google_calendar",
                          )
                        }
                      />
                    );
                  })}
                </ul>
              </div>
            ))
          ) : (
            <EmptyState
              icon={Plug}
              title="No services yet"
              description="Nothing can be connected yet."
            />
          )}
        </div>
      </Disclosure>
      {canSeeAll && <WebhooksSection labId={labId} />}
      {canSeeAll && (
        <Disclosure card region title="Everyone's connections">
          <div className="grid gap-3">
            <DataTable
              columns={cols}
              rows={everyone.data ?? []}
              getRowKey={(a) => a.id}
              loading={everyone.isLoading}
              empty={
                <EmptyState
                  title="No connections yet"
                  description="Connections made by lab members appear here."
                />
              }
            />
            <LabAiApps labId={labId} />
          </div>
        </Disclosure>
      )}
      <ConnectDialog labId={labId} provider={keyed} onClose={() => setKeyed(null)} />
      <Dialog open={!!confirm} onOpenChange={(open) => !open && setConfirm(null)}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">{confirm?.title}</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            {confirm?.description}
          </DialogDescription>
          {confirm?.calendar && (
            <div className="flex items-start gap-2 text-sm">
              <input
                id="delete-app-calendar"
                type="checkbox"
                checked={deleteCalendar}
                onChange={(e) => setDeleteCalendar(e.target.checked)}
                aria-describedby="delete-app-calendar-hint"
                className="mt-0.5"
              />
              <div className="grid gap-1">
                <label htmlFor="delete-app-calendar">
                  Also delete the labbenchos calendar from your Google Calendar
                </label>
                <span id="delete-app-calendar-hint" className="text-xs text-muted-foreground">
                  Otherwise it stays in Google Calendar until you delete it there. Meetings on your
                  main calendar stay either way.
                </span>
              </div>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button variant="destructive" disabled={disconnect.isPending} onClick={run}>
              {confirm?.action}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** Claude and other AI apps connect through the MCP address, not an OAuth service; Settings > AI
 * holds the full list and Revoke. */
function AiAppsSection() {
  const apps = (useAiGrants().data ?? []).filter((g) => g.kind === "oauth" && !g.revoked_at);
  return (
    <Disclosure card region title="Claude and other AI apps">
      <div className="grid gap-3">
        <div className="grid gap-3 rounded-lg border bg-background px-4 py-3">
          <p className="text-sm text-muted-foreground">
            {apps.length
              ? `Connected: ${apps.map((g) => g.client_name).join(", ")}.`
              : "No AI app connected."}{" "}
            They see only what you can see, in the labs you choose.{" "}
            <Link to="/settings#ai" className="font-medium text-foreground underline">
              Manage in Settings
            </Link>
          </p>
          <ConnectClaude />
        </div>
      </div>
    </Disclosure>
  );
}

/** Members' AI apps and tokens that can read this lab (the same list as Settings > AI). */
function LabAiApps({ labId }: { labId: string }) {
  const aiApps = useLabAiGrants(labId).data ?? [];
  if (aiApps.length === 0) return null;
  return (
    <>
      <h3 className="text-sm font-medium text-muted-foreground">
        Claude and other AI apps that can read this lab
      </h3>
      <ul className="grid gap-2 text-sm">
        {aiApps.map((g) => (
          <li key={g.id} className="rounded-lg border bg-background px-4 py-2">
            {g.user.display_name || g.user.email}:{" "}
            {g.kind === "oauth" ? g.client_name : `token "${g.name}"`} (
            {g.access === "write" ? "read and write" : "read only"}). Remove access in{" "}
            <Link to="/settings#ai" className="underline">
              Settings
            </Link>
            .
          </li>
        ))}
      </ul>
    </>
  );
}

/** A card is one provider, or (D262) the providers one sign-in covers, primary first. */
type Members = IntegrationProvider[];

function toCards(list: IntegrationProvider[]): Members[] {
  const taken = new Set<string>();
  const cards: Members[] = [];
  for (const p of list) {
    if (taken.has(p.name)) continue;
    const others = list.filter((q) => p.bundle.includes(q.name) && !taken.has(q.name));
    for (const m of [p, ...others]) taken.add(m.name);
    cards.push([p, ...others]);
  }
  return cards;
}

function groupByCategory(list: IntegrationProvider[]): [string, string, Members[]][] {
  const known = CATEGORIES.map(([k]) => k);
  const cards = toCards(list);
  const one = (c: Members) => c.length === 1;
  // One sign-in for several services gets a group of its own, named for the sign-in, on top.
  const bundles = [...new Set(cards.filter((c) => !one(c)).map((c) => c[0]!.bundle_label))];
  const groups: [string, string, Members[]][] = [
    ...bundles.map((b): [string, string, Members[]] => [
      `bundle:${b}`,
      b,
      cards.filter((c) => !one(c) && c[0]!.bundle_label === b),
    ]),
    ...CATEGORIES.map(([k, l]): [string, string, Members[]] => [
      k,
      l,
      cards.filter((c) => one(c) && c[0]!.category === k),
    ]),
  ];
  groups.push(["other", "Other", cards.filter((c) => one(c) && !known.includes(c[0]!.category))]);
  return groups.filter((g) => g[2].length > 0);
}

function ProviderCard({
  p,
  busy,
  onConnect,
  onDisconnect,
}: {
  p: IntegrationProvider;
  busy: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
}) {
  const status = p.account?.status;
  const retry = needsReconnect(status);
  const connectable = p.auth_type === "oauth2" || p.auth_type === "api_key";
  let action = null;
  let note = "";
  if (p.auth_type === "link_only") note = "No connection needed. Paste a link to attach it.";
  else if (p.auth_type === "public") note = "No connection needed. Links to public records.";
  else if (connectable && !p.configured && p.auth_type === "oauth2")
    action = <NotSetUp label={p.label} />;
  else if (connectable && status === "active")
    action = (
      <Button variant="outline" onClick={onDisconnect} aria-label={`Disconnect ${p.label}`}>
        Disconnect
      </Button>
    );
  else if (connectable)
    action = (
      <Button
        disabled={busy}
        onClick={onConnect}
        aria-label={`${retry ? "Reconnect" : "Connect"} ${p.label}`}
      >
        {retry ? "Reconnect" : "Connect"}
      </Button>
    );
  const who = p.account ? p.account.external_email || p.account.instance_url || "Account" : "";
  const help = status && status !== "active" ? `. ${STATUS_HELP[status] ?? ""}` : "";
  return (
    <li className="flex flex-wrap items-center justify-between gap-4 rounded-lg border bg-background px-4 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <ProviderIcon name={p.icon} className="size-5 shrink-0 text-muted-foreground" />
        <div className="grid min-w-0">
          <span className="text-sm font-medium">{p.label}</span>
          <span className="text-xs text-muted-foreground">
            {note || (p.account ? `${who}${help}` : "Not connected")}
          </span>
          <WhatItDoes p={p} />
        </div>
      </div>
      <div className="flex items-center gap-3">
        {status && <StatusBadge status={status} />}
        {action}
      </div>
    </li>
  );
}

/** Until the site has this service's app details (see .env.example) it cannot be connected, so
 * there is no button, only a plain note. */
function NotSetUp({ label }: { label: string }) {
  return (
    <span
      className="rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground"
      title={`${label} is not switched on for this site yet. Ask your lab admin to check back later.`}
    >
      Not available yet
    </span>
  );
}

/** What connecting each Google service lets labbenchos do, shown next to its Connect button. */
const DISCLOSURE: Record<string, string> = {
  google_drive:
    "Only files you pick or that labbenchos creates. The assistant reads a file only when you ask.",
  google_calendar:
    "Adds meetings you schedule, with a Meet link, to your calendar. Shows your events only to you. The labbenchos calendar stays off until you turn it on.",
  google_chat:
    "Lists your conversations so you can pick one. Reads and posts messages only in a conversation synced with a chat here, and reads one you choose to import.",
};

function WhatItDoes({ p }: { p: IntegrationProvider }) {
  const text = DISCLOSURE[p.name];
  return text ? <span className="text-xs text-muted-foreground">{text}</span> : null;
}

/** One sign-in for several services (D262), for example Google's Drive, Calendar and Meet. */
function BundleCard({
  members,
  busy,
  onConnect,
  onDisconnect,
}: {
  members: Members;
  busy: boolean;
  onConnect: () => void;
  onDisconnect: (accountId: string, what: string, calendar: boolean) => void;
}) {
  const primary = members[0]!;
  const group = primary.bundle_label;
  const short = (m: IntegrationProvider) => m.label.replace(new RegExp(`^${group}\\s+`), "");
  const joined = (list: Members) => list.map(short).join(", ");
  const active = members.filter((m) => m.account?.status === "active");
  const missing = members.filter((m) => m.account?.status !== "active");
  const stale = members.find((m) => m.account && needsReconnect(m.account.status));
  const who = active[0]?.account?.external_email || "your Google account";
  const hasCalendar = active.some((m) => m.name === "google_calendar");
  let note = "Not connected";
  let action: ReactNode;
  if (!primary.configured) action = <NotSetUp label={group} />;
  else if (active.length === members.length) {
    note = who;
    action = (
      <Button
        variant="outline"
        aria-label={`Disconnect ${group}`}
        onClick={() => onDisconnect(active[0]!.account!.id, joined(members), hasCalendar)}
      >
        Disconnect
      </Button>
    );
  } else {
    if (active.length > 0) note = `${who}. Not yet added: ${joined(missing)}`;
    else if (stale) note = `${STATUS_HELP[stale.account!.status] ?? "Needs reconnecting."}`;
    const verb = stale ? "Reconnect" : active.length > 0 ? `Add ${joined(missing)}` : "Connect";
    action = (
      <>
        {active.length > 0 && (
          // Only part of the sign-in was allowed: it can still be disconnected.
          <Button
            variant="outline"
            aria-label={`Disconnect ${group}`}
            onClick={() => onDisconnect(active[0]!.account!.id, joined(active), hasCalendar)}
          >
            Disconnect
          </Button>
        )}
        <Button disabled={busy} onClick={onConnect} aria-label={`${verb} ${group}`}>
          {verb}
        </Button>
      </>
    );
  }
  return (
    <li className="flex flex-wrap items-center justify-between gap-4 rounded-lg border bg-background px-4 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <ProviderIcon name={primary.icon} className="size-5 shrink-0 text-muted-foreground" />
        <div className="grid min-w-0">
          <span className="text-sm font-medium">{joined(members)}</span>
          <span className="text-xs text-muted-foreground">{note}</span>
          {members.map((m) => (
            <WhatItDoes key={m.name} p={m} />
          ))}
        </div>
      </div>
      <div className="flex items-center gap-3">
        {active.length === members.length && <StatusBadge status="active" />}
        {action}
      </div>
    </li>
  );
}

/** Where the server sends the browser when it does not know the lab (for example a lost session). */
export function IntegrationsErrorPage() {
  const [params] = useSearchParams();
  return (
    <EmptyState
      title="Could not connect"
      description={
        connectError(params.get("code")) ?? "Open a lab and try again from Integrations."
      }
    />
  );
}
