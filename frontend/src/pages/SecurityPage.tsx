import QRCode from "qrcode";
import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ProviderButton } from "@/components/auth/ProviderButton";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ReauthCancelled,
  useActivateTotp,
  useAuth,
  useDeactivateTotp,
  useDisconnectProvider,
  useEmailAction,
  useEmails,
  useProviderAccounts,
  useProviders,
  useRecoveryCodes,
  useRegenerateRecoveryCodes,
  useTotp,
} from "@/hooks/auth";
import { useReauth } from "@/hooks/reauth";
import { ApiError } from "@/lib/api";
import { APP_NAME } from "@/lib/constants";
import { formErrors } from "@/lib/forms";

type Reauth = ReturnType<typeof useReauth>;
const REAUTH = "For your safety, sign out and sign back in, then try this again.";
const msg = (e: unknown) =>
  e instanceof ReauthCancelled
    ? undefined
    : e instanceof ApiError && e.status === 401
      ? REAUTH
      : formErrors(e, []).form;

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="grid gap-4 rounded-lg border p-6">
      <div>
        <h2 className="text-base font-semibold">{title}</h2>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      {children}
    </section>
  );
}

function Qr({ uri }: { uri: string }) {
  const [src, setSrc] = useState<string>();
  useEffect(() => {
    let live = true;
    QRCode.toDataURL(uri, { margin: 1, width: 192 }).then(
      (s) => live && setSrc(s),
      () => undefined, // The secret below is the fallback.
    );
    return () => {
      live = false;
    };
  }, [uri]);
  return src ? (
    <img
      src={src}
      alt="QR code for your authenticator app"
      className="size-48 rounded-md border bg-white"
    />
  ) : null;
}

function RecoveryCodes({ run }: { run: Reauth["run"] }) {
  const codes = useRecoveryCodes(true);
  const regenerate = useRegenerateRecoveryCodes();
  const [error, setError] = useState<string>();
  const unused = codes.data?.unused_codes ?? [];

  return (
    <div className="grid gap-3">
      <h3 className="text-sm font-medium">Recovery codes</h3>
      <p className="text-xs text-muted-foreground">
        Each code works once if you lose your phone. Keep them somewhere safe.
      </p>
      {codes.isLoading ? (
        <Skeleton className="h-20 w-64" />
      ) : unused.length > 0 ? (
        <ul className="grid w-64 grid-cols-2 gap-1 rounded-md border p-3 font-mono text-sm">
          {unused.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      ) : (
        <p className="text-sm">
          {codes.data
            ? `${codes.data.unused_code_count} unused codes left.`
            : "No recovery codes yet."}
        </p>
      )}
      <FormError message={error} />
      <Button
        variant="outline"
        className="justify-self-start"
        disabled={regenerate.isPending}
        onClick={() => {
          setError(undefined);
          run(() => regenerate.mutateAsync()).then(
            () => toast.success("New recovery codes created"),
            (e) => setError(msg(e)),
          );
        }}
      >
        Create new recovery codes
      </Button>
    </div>
  );
}

function TotpSection({ run }: { run: Reauth["run"] }) {
  const { email } = useAuth();
  const totp = useTotp();
  const activate = useActivateTotp();
  const deactivate = useDeactivateTotp();
  const [error, setError] = useState<string>();
  const [settingUp, setSettingUp] = useState(false);

  async function enable(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const code = String(new FormData(e.currentTarget).get("code") ?? "").trim();
    if (!code) return setError("Enter the 6-digit code from your app");
    setError(undefined);
    try {
      await run(() => activate.mutateAsync(code));
      toast.success("Two-step verification is on");
    } catch (err) {
      setError(msg(err));
    }
  }

  let body: React.ReactNode;
  if (totp.isLoading) body = <Skeleton className="h-24 w-64" />;
  else if (totp.error) body = <FormError message={msg(totp.error)} />;
  else if (totp.data?.enabled)
    body = (
      <>
        <p className="text-sm">
          Two-step verification is on. You will be asked for a code when you sign in.
        </p>
        <FormError message={error} />
        <Button
          variant="destructive"
          className="justify-self-start"
          disabled={deactivate.isPending}
          onClick={() => {
            setError(undefined);
            run(() => deactivate.mutateAsync()).then(
              () => {
                setSettingUp(false);
                toast.success("Two-step verification is off");
              },
              (e) => setError(msg(e)),
            );
          }}
        >
          Turn off two-step verification
        </Button>
        <RecoveryCodes run={run} />
      </>
    );
  else if (!settingUp)
    body = (
      <Button className="justify-self-start" onClick={() => setSettingUp(true)}>
        Set up two-step verification
      </Button>
    );
  else {
    const secret = totp.data?.secret ?? "";
    const uri = `otpauth://totp/${encodeURIComponent(APP_NAME)}:${encodeURIComponent(email ?? "")}?secret=${secret}&issuer=${encodeURIComponent(APP_NAME)}`;
    body = (
      <form onSubmit={enable} noValidate className="grid gap-4">
        <ol className="grid list-decimal gap-1 pl-5 text-sm">
          <li>Open an authenticator app such as 1Password, Authy or Google Authenticator.</li>
          <li>Scan the QR code, or type in the setup key.</li>
          <li>Enter the 6-digit code the app shows.</li>
        </ol>
        {secret && <Qr uri={uri} />}
        <p className="text-sm">
          Setup key: <code className="rounded-md bg-muted px-1.5 py-0.5 font-mono">{secret}</code>
        </p>
        <div className="max-w-xs">
          <FormField label="6-digit code" error={error}>
            {(p) => <Input {...p} name="code" inputMode="numeric" autoComplete="one-time-code" />}
          </FormField>
        </div>
        <Button type="submit" className="justify-self-start" disabled={activate.isPending}>
          Turn on two-step verification
        </Button>
      </form>
    );
  }

  return (
    <Section
      title="Two-step verification"
      description="Add a code from your phone to protect your account."
    >
      {body}
    </Section>
  );
}

function ConnectedAccountsSection({ reauth }: { reauth: Reauth }) {
  const { hasUsablePassword } = useAuth();
  const totp = useTotp();
  const providers = useProviders();
  const accounts = useProviderAccounts();
  const disconnect = useDisconnectProvider();
  const [error, setError] = useState<string>();
  const google = providers.data?.find((p) => p.id === "google");
  const connected = accounts.data?.find((a) => a.provider.id === "google");

  if (!google && !connected) return null;
  return (
    <Section title="Connected accounts" description="Sign in with Google instead of a password.">
      <div className="flex items-center justify-between gap-4">
        <div className="text-sm">
          <p className="font-medium">Google</p>
          <p className="text-muted-foreground">
            {accounts.isLoading ? "Loading..." : connected ? connected.display : "Not connected"}
          </p>
        </div>
        {connected ? (
          <Button
            variant="outline"
            disabled={!hasUsablePassword || disconnect.isPending}
            onClick={() => {
              setError(undefined);
              reauth
                .run(() => disconnect.mutateAsync(connected))
                .then(
                  () => toast.success("Google disconnected"),
                  (e) => setError(msg(e)),
                );
            }}
          >
            Disconnect
          </Button>
        ) : (
          <div className="w-48">
            <ProviderButton
              process="connect"
              label="Connect Google"
              returnTo="/account"
              beforeSubmit={async () => {
                // Connecting leaves the page, so ask first (nothing to prove without a password or MFA).
                const flows = { password: hasUsablePassword, mfa: !!totp.data?.enabled };
                if (flows.password || flows.mfa) await reauth.ensure(flows);
              }}
            />
          </div>
        )}
      </div>
      {connected && !hasUsablePassword && (
        <p className="text-xs text-muted-foreground">
          You sign in only with Google. Set a password first (use Forgot password on the sign-in
          page), then you can disconnect.
        </p>
      )}
      <FormError message={error} />
    </Section>
  );
}

function EmailSection({ run: reauthRun }: { run: Reauth["run"] }) {
  const emails = useEmails();
  const act = useEmailAction();
  const [error, setError] = useState<string>();

  function run(op: "add" | "remove" | "primary" | "resend", email: string, ok: string) {
    setError(undefined);
    return reauthRun(() => act.mutateAsync({ op, email })).then(
      () => (toast.success(ok), true),
      (e) => (setError(msg(e)), false),
    );
  }

  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const email = String(new FormData(form).get("email") ?? "").trim();
    if (!email) return setError("Enter an email address");
    if (await run("add", email, "Check that inbox to confirm the address")) form.reset();
  }

  return (
    <Section
      title="Email addresses"
      description="Lab invitations work with any verified address on your account."
    >
      {emails.isLoading ? (
        <Skeleton className="h-16 w-full" />
      ) : (
        <ul className="grid divide-y rounded-md border">
          {(emails.data ?? []).map((m) => (
            <li key={m.email} className="flex flex-wrap items-center gap-2 p-3 text-sm">
              <span className="mr-auto font-medium">{m.email}</span>
              {m.primary && <Badge>Primary</Badge>}
              <Badge variant={m.verified ? "secondary" : "outline"}>
                {m.verified ? "Verified" : "Not verified"}
              </Badge>
              {!m.verified && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={act.isPending}
                  onClick={() => void run("resend", m.email, "Verification email sent")}
                >
                  Resend verification
                </Button>
              )}
              {m.verified && !m.primary && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={act.isPending}
                  onClick={() => void run("primary", m.email, "Primary email changed")}
                >
                  Make primary
                </Button>
              )}
              {!m.primary && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={act.isPending}
                  onClick={() => void run("remove", m.email, "Email removed")}
                >
                  Remove
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={add} noValidate className="grid max-w-sm gap-4">
        <FormField label="Add an email address" error={error}>
          {(p) => <Input maxLength={254} {...p} name="email" type="email" autoComplete="email" />}
        </FormField>
        <Button type="submit" className="justify-self-start" disabled={act.isPending}>
          Add email
        </Button>
      </form>
    </Section>
  );
}

/** Email, connected accounts and two-step verification; embedded in Settings (Run 4). */
export function SecuritySections() {
  const reauth = useReauth();
  return (
    <>
      {reauth.dialog}
      <div className="grid max-w-2xl gap-8">
        <EmailSection run={reauth.run} />
        <ConnectedAccountsSection reauth={reauth} />
        <TotpSection run={reauth.run} />
      </div>
    </>
  );
}
