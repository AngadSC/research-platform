import QRCode from "qrcode";
import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useActivateTotp,
  useAuth,
  useDeactivateTotp,
  useRecoveryCodes,
  useRegenerateRecoveryCodes,
  useTotp,
} from "@/hooks/auth";
import { useMe, useUpdateMe } from "@/hooks/workspace";
import { ApiError } from "@/lib/api";
import { APP_NAME } from "@/lib/constants";
import { formErrors } from "@/lib/forms";

const REAUTH = "For your safety, sign out and sign back in, then try this again.";
const msg = (e: unknown) =>
  e instanceof ApiError && e.status === 401 ? REAUTH : formErrors(e, []).form;

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

function NameSection() {
  const { data: me } = useMe();
  const update = useUpdateMe();
  const [error, setError] = useState<string>();

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const display_name = String(new FormData(e.currentTarget).get("name") ?? "").trim();
    if (!display_name) return setError("Enter your name");
    setError(undefined);
    try {
      await update.mutateAsync({ display_name });
      toast.success("Saved");
    } catch (err) {
      setError(msg(err));
    }
  }

  return (
    <Section title="Your name" description="Shown to other people in your labs.">
      {me ? (
        <form onSubmit={submit} noValidate className="grid max-w-sm gap-4">
          <FormField label="Name" error={error}>
            {(p) => <Input {...p} name="name" defaultValue={me.display_name} autoComplete="name" />}
          </FormField>
          <Button type="submit" className="justify-self-start" disabled={update.isPending}>
            Save
          </Button>
        </form>
      ) : (
        <Skeleton className="h-9 w-64" />
      )}
    </Section>
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

function RecoveryCodes() {
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
          regenerate.mutateAsync().then(
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

function TotpSection() {
  const { email } = useAuth();
  const totp = useTotp();
  const activate = useActivateTotp();
  const deactivate = useDeactivateTotp();
  const [error, setError] = useState<string>();

  async function enable(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const code = String(new FormData(e.currentTarget).get("code") ?? "").trim();
    if (!code) return setError("Enter the 6-digit code from your app");
    setError(undefined);
    try {
      await activate.mutateAsync(code);
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
            deactivate.mutateAsync().then(
              () => toast.success("Two-step verification is off"),
              (e) => setError(msg(e)),
            );
          }}
        >
          Turn off two-step verification
        </Button>
        <RecoveryCodes />
      </>
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

export function SecurityPage() {
  return (
    <>
      <PageHeader title="Account" description="Your name and sign-in security." />
      <div className="grid max-w-2xl gap-8">
        <NameSection />
        <TotpSection />
      </div>
    </>
  );
}
