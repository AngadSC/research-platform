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
import { useLab } from "@/hooks/workspace";
import type { ConnectedAccount, IntegrationProvider } from "@/lib/api-types";
import { personName } from "@/lib/api-types";
import { useRegisterCommands } from "@/lib/commands";
import { formErrors } from "@/lib/forms";
import { CATEGORIES, connectError, needsReconnect, STATUS_HELP } from "@/lib/integrations";
import { WebhooksSection } from "@/pages/settings/WebhooksSection";

interface Confirm {
  id: string;
  title: string;
  description: string;
  action: "Revoke" | "Disconnect";
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
  const [initialError] = useState(() => params.get("error"));
  const [failure, setFailure] = useState<string>();
  const [keyed, setKeyed] = useState<IntegrationProvider | null>(null);

  // The server sends the browser back here with ?connected=<service> or ?error=<code>.
  const connected = params.get("connected");
  const errorCode = params.get("error");
  const label = (name: string) => providers.data?.find((p) => p.name === name)?.label ?? name;
  const loaded = !!providers.data;
  useEffect(() => {
    if (connected && loaded) toast.success(`${label(connected)} connected`);
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
    disconnect.mutate(confirm.id, {
      onSuccess: () =>
        toast.success(confirm.action === "Revoke" ? "Connection revoked" : "Disconnected"),
      onError: (e) => toast.error(formErrors(e, []).form ?? "Something went wrong."),
      onSettled: () => setConfirm(null),
    });
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
        description="Connect outside services to link their files to your projects. We only read details such as titles and modified times."
      />
      <p className="text-sm text-muted-foreground">
        Each person connects their own accounts here. Using Claude or ChatGPT?{" "}
        <Link to="/settings#ai" className="font-medium text-foreground underline">
          Connect them in Settings, under AI
        </Link>
        .
      </p>
      <FormError message={failure ?? connectError(initialError)} />
      <section aria-labelledby="services" className="grid gap-3">
        <h2 id="services" className="text-base font-semibold">
          Services
        </h2>
        {providers.data?.some((p) => p.auth_type === "oauth2" && !p.configured) && (
          <p className="text-sm text-muted-foreground">
            A dimmed Connect button means whoever runs this site has not added that service&apos;s
            app details yet. It is a one-time setup for the whole site. Once it is done, everyone
            here can connect their own account with one click.
          </p>
        )}
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
                  const disconnectWith = (id: string, title: string, extra: string) =>
                    setConfirm({
                      id,
                      action: "Disconnect",
                      title,
                      description: `${extra}Linked items stay in your projects, but we stop checking them until you connect again.`,
                    });
                  return members.length > 1 ? (
                    <BundleCard
                      key={p.name}
                      members={members}
                      busy={connect.isPending}
                      onConnect={onConnect}
                      onDisconnect={(id, what) =>
                        disconnectWith(
                          id,
                          `Disconnect ${p.bundle_label}?`,
                          `This disconnects ${what} together, because they use one sign-in. `,
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
                        p.account && disconnectWith(p.account.id, `Disconnect ${p.label}?`, "")
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
      </section>
      {canSeeAll && <WebhooksSection labId={labId} />}
      {canSeeAll && (
        <section aria-labelledby="everyone" className="grid gap-3">
          <h2 id="everyone" className="text-base font-semibold">
            Everyone&apos;s connections
          </h2>
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
        </section>
      )}
      <ConnectDialog labId={labId} provider={keyed} onClose={() => setKeyed(null)} />
      <Dialog open={!!confirm} onOpenChange={(open) => !open && setConfirm(null)}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">{confirm?.title}</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            {confirm?.description}
          </DialogDescription>
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
        </div>
      </div>
      <div className="flex items-center gap-3">
        {status && <StatusBadge status={status} />}
        {action}
      </div>
    </li>
  );
}

/** The button is always there, so people can see it exists; until whoever runs the site adds the
 * app details (see .env.example) it cannot be used, and the note says why. */
function NotSetUp({ label }: { label: string }) {
  return (
    <>
      <span className="text-xs text-muted-foreground">Not set up on this server</span>
      <span title="Whoever runs this site needs to add this service's app details once. After that, anyone can connect.">
        <Button disabled aria-label={`Connect ${label} (not set up on this server)`}>
          Connect
        </Button>
      </span>
    </>
  );
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
  onDisconnect: (accountId: string, what: string) => void;
}) {
  const primary = members[0]!;
  const group = primary.bundle_label;
  const short = (m: IntegrationProvider) => m.label.replace(new RegExp(`^${group}\\s+`), "");
  const joined = (list: Members) => list.map(short).join(", ");
  const active = members.filter((m) => m.account?.status === "active");
  const missing = members.filter((m) => m.account?.status !== "active");
  const stale = members.find((m) => m.account && needsReconnect(m.account.status));
  const who = active[0]?.account?.external_email || "your Google account";
  let note = "Not connected";
  let action: ReactNode;
  if (!primary.configured) action = <NotSetUp label={group} />;
  else if (active.length === members.length) {
    note = who;
    action = (
      <Button
        variant="outline"
        aria-label={`Disconnect ${group}`}
        onClick={() => onDisconnect(active[0]!.account!.id, joined(members))}
      >
        Disconnect
      </Button>
    );
  } else {
    if (active.length > 0) note = `${who}. Not yet added: ${joined(missing)}`;
    else if (stale) note = `${STATUS_HELP[stale.account!.status] ?? "Needs reconnecting."}`;
    const verb = stale ? "Reconnect" : active.length > 0 ? `Add ${joined(missing)}` : "Connect";
    action = (
      <Button disabled={busy} onClick={onConnect} aria-label={`${verb} ${group}`}>
        {verb}
      </Button>
    );
  }
  return (
    <li className="flex flex-wrap items-center justify-between gap-4 rounded-lg border bg-background px-4 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <ProviderIcon name={primary.icon} className="size-5 shrink-0 text-muted-foreground" />
        <div className="grid min-w-0">
          <span className="text-sm font-medium">{joined(members)}</span>
          <span className="text-xs text-muted-foreground">{note}</span>
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
