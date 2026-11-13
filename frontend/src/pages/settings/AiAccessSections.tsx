import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { RelativeTime } from "@/components/shared/RelativeTime";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  mcpUrl,
  useAiGrants,
  useCreatePat,
  useLabAiGrants,
  useRemoveLabGrant,
  useRevokeGrant,
  type Access,
  type AiGrant,
  type PatCreated,
} from "@/hooks/ai";
import { ReauthCancelled } from "@/hooks/auth";
import { useReauth } from "@/hooks/reauth";
import { useLabs } from "@/hooks/workspace";
import { formErrors } from "@/lib/forms";
import { NativeSelect, Section } from "@/pages/admin/common";

/** Why the system disconnected an AI app or token (D195). */
const ENDED: Record<string, string> = {
  password_changed: "your password was changed",
  password_reset: "your password was reset",
  mfa_removed: "two-factor authentication was removed from your account",
  deactivated: "your account was deactivated",
};

function EndedNotice({ grants }: { grants: AiGrant[] }) {
  if (grants.length === 0) return null;
  return (
    <div role="status" className="grid gap-1 rounded-md border border-warning/40 p-3 text-sm">
      <p className="font-medium">Some AI connections were disconnected for your security.</p>
      <ul className="list-disc pl-5">
        {grants.map((g) => (
          <li key={g.id}>
            {g.kind === "oauth" ? g.client_name : `Token "${g.name}"`} stopped working because{" "}
            {ENDED[g.revoked_reason ?? ""] ?? "your account security changed"}. Connect it again if
            you still want it.
          </li>
        ))}
      </ul>
    </div>
  );
}

const CLAUDE_CONNECT =
  "https://claude.ai/customize/connectors?modal=add-custom-connector&connectorName=labbenchos&connectorUrl=";

function copy(text: string) {
  (navigator.clipboard?.writeText(text) ?? Promise.reject(new Error("no clipboard"))).then(
    () => toast.success("Copied."),
    () => toast.error("Copy failed; select the text instead."),
  );
}

/** The three steps to connect Claude (also on Help). */
export function ClaudeSteps() {
  return (
    <div className="text-sm">
      <ol className="list-decimal pl-5 text-muted-foreground">
        <li>Click Connect to Claude. claude.ai opens with labbenchos filled in.</li>
        <li>
          Click Add, then sign in to labbenchos, choose which labs Claude may see and click Allow.
        </li>
        <li>In a Claude chat, turn on labbenchos from the tools menu.</li>
      </ol>
      <p className="mt-1 text-muted-foreground">
        Custom connectors need a Claude plan that supports them.
      </p>
    </div>
  );
}

/** "Connect to Claude", its steps, "Copy address" and the connection address (also shown on
 * Integrations). */
export function ConnectClaude() {
  return (
    <>
      <ClaudeSteps />
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" asChild>
          <a
            href={CLAUDE_CONNECT + encodeURIComponent(mcpUrl())}
            target="_blank"
            rel="noopener noreferrer"
          >
            Connect to Claude
          </a>
        </Button>
        <Button size="sm" variant="outline" onClick={() => copy(mcpUrl())}>
          Copy address
        </Button>
      </div>
      <p className="text-sm">
        Connection address: <code className="break-all">{mcpUrl()}</code>
      </p>
    </>
  );
}

const accessLabel = (a: string) => (a === "write" ? "Read and write" : "Read only");

function GrantMeta({ g }: { g: AiGrant }) {
  return (
    <p className="text-sm text-muted-foreground">
      {g.labs.map((l) => l.name).join(", ")} · {accessLabel(g.access)} · last used{" "}
      {g.last_used_at ? <RelativeTime value={g.last_used_at} /> : "never"}
      {g.expires_at && (
        <>
          {" "}
          · expires <RelativeTime value={g.expires_at} />
        </>
      )}
    </p>
  );
}

function GrantList({ grants, empty }: { grants: AiGrant[]; empty: string }) {
  const revoke = useRevokeGrant();
  if (grants.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul className="grid gap-3">
      {grants.map((g) => (
        <li key={g.id} className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium">{g.kind === "oauth" ? g.client_name : g.name}</p>
            <GrantMeta g={g} />
          </div>
          <Button
            variant="outline"
            size="sm"
            aria-label={`Revoke ${g.kind === "oauth" ? g.client_name : g.name}`}
            disabled={revoke.isPending}
            onClick={() =>
              revoke.mutate(g.id, {
                onSuccess: () => toast.success("Access revoked."),
                onError: () => toast.error("Could not revoke. Try again."),
              })
            }
          >
            Revoke
          </Button>
        </li>
      ))}
    </ul>
  );
}

function LabChoice({
  selected,
  onChange,
}: {
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  const labs = useLabs().data ?? [];
  return (
    <fieldset className="grid gap-1">
      <legend className="mb-1 text-sm font-medium">Labs</legend>
      {labs.map((lab) => (
        <label key={lab.id} className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={selected.includes(lab.id)}
            onChange={(e) =>
              onChange(
                e.target.checked ? [...selected, lab.id] : selected.filter((id) => id !== lab.id),
              )
            }
          />
          {lab.name}
        </label>
      ))}
    </fieldset>
  );
}

function NewToken({ created, onDone }: { created: PatCreated; onDone: () => void }) {
  const command = `claude mcp add --transport http labbenchos ${mcpUrl()} --header "Authorization: Bearer ${created.token}"`;
  return (
    <div className="grid gap-3 rounded-md bg-muted p-4" role="status">
      <p className="text-sm font-medium">
        Copy your token now. It is shown only once; we keep just a fingerprint of it.
      </p>
      <code className="text-sm break-all" aria-label="New access token">
        {created.token}
      </code>
      <p className="text-sm text-muted-foreground">For Claude Code:</p>
      <code className="text-xs break-all">{command}</code>
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => copy(created.token)}>
          Copy token
        </Button>
        <Button size="sm" onClick={onDone}>
          Done
        </Button>
      </div>
    </div>
  );
}

function CreateToken() {
  const create = useCreatePat();
  const reauth = useReauth(); // D194: a token is a password, so a recent password check first
  const [labs, setLabs] = useState<string[]>([]);
  const [created, setCreated] = useState<PatCreated | null>(null);
  const errors = create.error ? formErrors(create.error, ["name", "labs"]) : { fields: {} };

  if (created) return <NewToken created={created} onDone={() => setCreated(null)} />;
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const body = {
      name: String(fd.get("name") ?? "").trim(),
      labs,
      access: fd.get("access") as Access,
      expires_in_days: Number(fd.get("expires")),
    };
    reauth
      .run(() => create.mutateAsync(body))
      .then(setCreated, (err) => {
        if (err instanceof ReauthCancelled) create.reset(); // the failure shown is already in `create.error`
      });
  };
  return (
    <>
      <form className="grid gap-3" onSubmit={submit} aria-label="Create an access token">
        <FormField label="Token name" error={errors.fields.name}>
          {(p) => (
            <Input
              {...p}
              name="name"
              required
              maxLength={100}
              placeholder="Claude Code on my laptop"
            />
          )}
        </FormField>
        <LabChoice selected={labs} onChange={setLabs} />
        {errors.fields.labs && (
          <p role="alert" className="text-sm text-destructive">
            {errors.fields.labs}
          </p>
        )}
        <FormField label="Access">
          {(p) => (
            <NativeSelect {...p} name="access" defaultValue="read">
              <option value="read">Read only</option>
              <option value="write">Read and write (create tasks, updates, draft decisions)</option>
            </NativeSelect>
          )}
        </FormField>
        <FormField label="Expires after">
          {(p) => (
            <NativeSelect {...p} name="expires" defaultValue="30">
              <option value="7">7 days</option>
              <option value="30">30 days</option>
              <option value="90">90 days</option>
              <option value="365">1 year</option>
            </NativeSelect>
          )}
        </FormField>
        <FormError message={"form" in errors ? errors.form : undefined} />
        <Button type="submit" className="w-fit" disabled={create.isPending || labs.length === 0}>
          Create token
        </Button>
      </form>
      {reauth.dialog}
    </>
  );
}

function LabAccess({ labId, labName }: { labId: string; labName: string }) {
  const grants = useLabAiGrants(labId).data ?? [];
  const remove = useRemoveLabGrant(labId);
  return (
    <Section
      title={`AI access to ${labName}`}
      description="Members' connected AI apps and tokens that can read this lab. Removing one takes this lab out of it at once."
    >
      {grants.length === 0 ? (
        <p className="text-sm text-muted-foreground">No AI app or token can read this lab.</p>
      ) : (
        <ul className="grid gap-3">
          {grants.map((g) => (
            <li key={g.id} className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-medium">
                  {g.user.display_name || g.user.email}:{" "}
                  {g.kind === "oauth" ? g.client_name : `token "${g.name}"`}{" "}
                  <Badge variant="outline">{g.kind === "oauth" ? "App" : "Token"}</Badge>
                </p>
                <GrantMeta g={g} />
              </div>
              <Button
                variant="outline"
                size="sm"
                disabled={remove.isPending}
                onClick={() =>
                  remove.mutate(g.id, {
                    onSuccess: () => toast.success("Access to this lab removed."),
                    onError: () => toast.error("Could not remove. Try again."),
                  })
                }
              >
                Remove access
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

/** Settings: "Connected AI apps", first on the AI tab so connecting Claude is not below the keys. */
export function ConnectedAiApps() {
  const all = useAiGrants().data ?? [];
  const grants = all.filter((g) => !g.revoked_at);
  const ended = all.filter((g) => g.revoked_at && g.revoked_reason);
  return (
    <Section
      title="Connected AI apps"
      description="Claude, ChatGPT and other AI apps you have connected. They see only what you can see, in the labs you chose."
    >
      <p className="text-sm">
        Read only is the default. Read and write also lets the app create tasks, post task updates
        and draft decisions.
      </p>
      <ConnectClaude />
      <div className="text-sm">
        <p className="font-medium">Using ChatGPT?</p>
        <ol className="list-decimal pl-5 text-muted-foreground">
          <li>In ChatGPT, open Settings and find Apps or Connectors.</li>
          <li>Turn on Developer mode, under Advanced settings. Not every plan has it.</li>
          <li>Choose Create, name it labbenchos and paste the connection address.</li>
          <li>Choose OAuth to sign in, then pick your labs on the page that opens.</li>
        </ol>
      </div>
      <EndedNotice grants={ended} />
      <GrantList grants={grants.filter((g) => g.kind === "oauth")} empty="No AI apps connected." />
    </Section>
  );
}

/** Settings: "Access tokens" and, for pi/lab_admin, each lab's AI access. */
export function AiAccessSections() {
  const grants = (useAiGrants().data ?? []).filter((g) => !g.revoked_at);
  const managed = (useLabs().data ?? []).filter((l) =>
    l.my_permissions.includes("manage_lab_integrations"),
  );
  return (
    <>
      <Section
        title="Access tokens"
        description="For AI tools that take a token instead of signing in, such as Claude Code. Treat a token like a password."
      >
        <GrantList grants={grants.filter((g) => g.kind === "pat")} empty="No access tokens." />
        <CreateToken />
      </Section>
      {managed.map((l) => (
        <LabAccess key={l.id} labId={l.id} labName={l.name} />
      ))}
    </>
  );
}
