import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useConnect } from "@/hooks/integrations";
import type { IntegrationProvider } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";

type Field = IntegrationProvider["connect_fields"][number];

/** The fields to ask for: what the registry lists, plus an instance URL when the provider is
 * self-hosted and did not list one. */
function fieldsFor(p: IntegrationProvider): Field[] {
  const fields = p.connect_fields;
  if (p.needs_instance_url && !fields.some((f) => f.name === "instance_url"))
    return [
      ...fields,
      { name: "instance_url", label: "Instance URL", help_text: "", required: true, secret: false },
    ];
  return fields;
}

/** Connect form for an API-key provider, built from its `connect_fields`. Secrets are password
 * inputs, are sent once and cleared as soon as the server answers. */
export function ConnectDialog({
  labId,
  provider,
  onClose,
}: {
  labId: string;
  provider: IntegrationProvider | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={!!provider} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        {provider && <ConnectForm key={provider.name} labId={labId} p={provider} done={onClose} />}
      </DialogContent>
    </Dialog>
  );
}

function ConnectForm({
  labId,
  p,
  done,
}: {
  labId: string;
  p: IntegrationProvider;
  done: () => void;
}) {
  const connect = useConnect(labId);
  const fields = fieldsFor(p);
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string>();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const missing: Record<string, string> = {};
    const body: Record<string, string> = {};
    for (const f of fields) {
      const v = (values[f.name] ?? "").trim();
      if (v) body[f.name] = v;
      else if (f.required) missing[f.name] = `Enter ${f.label.toLowerCase()}.`;
    }
    setErrors(missing);
    setFailure(undefined);
    if (Object.keys(missing).length) return;
    connect.mutate(
      { provider: p.name, body },
      {
        onSuccess: () => {
          toast.success(`${p.label} connected`);
          done();
        },
        onError: (err) => {
          const r = formErrors(
            err,
            fields.map((f) => f.name),
          );
          setErrors(Object.fromEntries(Object.entries(r.fields).map(([k, v]) => [k, String(v)])));
          setFailure(r.form);
        },
        // Whatever the answer, secrets do not stay in the form.
        onSettled: () =>
          setValues((cur) =>
            Object.fromEntries(
              Object.entries(cur).map(([k, v]) => [
                k,
                fields.find((f) => f.name === k)?.secret ? "" : v,
              ]),
            ),
          ),
      },
    );
  };

  return (
    <form onSubmit={submit} noValidate className="grid gap-4">
      <DialogTitle className="text-base font-semibold">Connect {p.label}</DialogTitle>
      <DialogDescription className="text-sm text-muted-foreground">
        We store the key encrypted and only read what this connection needs, such as titles and
        dates. It is never shown again.
      </DialogDescription>
      <FormError message={failure} />
      {fields.map((f) => (
        <FormField
          key={f.name}
          label={f.label}
          hint={f.help_text || undefined}
          error={errors[f.name]}
        >
          {(props) => (
            <Input
              {...props}
              name={f.name}
              type={f.secret ? "password" : f.name === "instance_url" ? "url" : "text"}
              autoComplete={f.secret ? "new-password" : "off"}
              value={values[f.name] ?? ""}
              onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
            />
          )}
        </FormField>
      ))}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={done}>
          Cancel
        </Button>
        <Button type="submit" disabled={connect.isPending}>
          Connect
        </Button>
      </div>
    </form>
  );
}
