import { useState, type FormEvent } from "react";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { reauthenticate, type ReauthFlows } from "@/hooks/auth";
import { formErrors } from "@/lib/forms";

export interface Ask {
  flows: ReauthFlows;
  done: () => void;
  cancel: () => void;
}

export function ReauthDialog({ ask }: { ask: Ask | null }) {
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!ask) return;
    const f = new FormData(e.currentTarget);
    const password = String(f.get("password") ?? "");
    const code = String(f.get("code") ?? "").trim();
    if (ask.flows.password && !password) return setError("Enter your password");
    if (ask.flows.mfa && !code) return setError("Enter the 6-digit code from your app");
    setBusy(true);
    try {
      await reauthenticate(ask.flows, { password, code });
      setError(undefined);
      ask.done();
    } catch (err) {
      setError(formErrors(err, []).form);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={!!ask} onOpenChange={(o) => !o && ask?.cancel()}>
      <DialogContent className="max-w-sm">
        <DialogTitle className="text-base font-semibold">Confirm it is you</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">
          For your safety, confirm your {ask?.flows.password ? "password" : "code"}
          {ask?.flows.password && ask.flows.mfa ? " and a code from your app" : ""} to continue.
        </DialogDescription>
        {ask && (
          <form onSubmit={submit} noValidate className="grid gap-4">
            {ask.flows.password && (
              <FormField label="Password">
                {(p) => (
                  <Input {...p} name="password" type="password" autoComplete="current-password" />
                )}
              </FormField>
            )}
            {ask.flows.mfa && (
              <FormField label="6-digit code">
                {(p) => (
                  <Input {...p} name="code" inputMode="numeric" autoComplete="one-time-code" />
                )}
              </FormField>
            )}
            <FormError message={error} />
            <Button type="submit" disabled={busy}>
              Continue
            </Button>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
