import { Plug } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
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
import { connectError, needsReconnect, STATUS_HELP } from "@/lib/integrations";

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
    connect.mutate(p.name, { onError: (e) => setFailure(formErrors(e, ["code"]).form) });
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
      <FormError message={failure ?? connectError(initialError)} />
      <section aria-labelledby="services" className="grid gap-3">
        <h2 id="services" className="text-base font-semibold">
          Services
        </h2>
        {providers.isLoading ? (
          <div aria-busy="true" aria-label="Loading" className="grid gap-2">
            <Skeleton className="h-16 w-full" />
          </div>
        ) : providers.data?.length ? (
          <ul className="grid divide-y rounded-lg border bg-background">
            {providers.data.map((p) => (
              <ProviderRow
                key={p.name}
                p={p}
                busy={connect.isPending}
                onConnect={() => start(p)}
                onDisconnect={() =>
                  p.account &&
                  setConfirm({
                    id: p.account.id,
                    action: "Disconnect",
                    title: `Disconnect ${p.label}?`,
                    description:
                      "Linked items stay in your projects, but we stop checking them until you connect again.",
                  })
                }
              />
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={Plug}
            title="No services yet"
            description="Nothing can be connected yet."
          />
        )}
      </section>
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

function ProviderRow({
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
  let action = null;
  if (p.auth_type === "oauth2") {
    if (!p.configured)
      action = (
        <span className="text-xs text-muted-foreground">Not set up for your institution</span>
      );
    else if (status === "active")
      action = (
        <Button variant="outline" onClick={onDisconnect} aria-label={`Disconnect ${p.label}`}>
          Disconnect
        </Button>
      );
    else
      action = (
        <Button
          disabled={busy}
          onClick={onConnect}
          aria-label={`${retry ? "Reconnect" : "Connect"} ${p.label}`}
        >
          {retry ? "Reconnect" : "Connect"}
        </Button>
      );
  }
  const who = p.account ? p.account.external_email || "Account" : "";
  const help = status && status !== "active" ? `. ${STATUS_HELP[status] ?? ""}` : "";
  return (
    <li className="flex flex-wrap items-center justify-between gap-4 px-4 py-3">
      <div className="flex items-center gap-3">
        <ProviderIcon name={p.icon} className="size-5 text-muted-foreground" />
        <div className="grid">
          <span className="text-sm font-medium">{p.label}</span>
          <span className="text-xs text-muted-foreground">
            {p.account ? `${who}${help}` : "Not connected"}
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
