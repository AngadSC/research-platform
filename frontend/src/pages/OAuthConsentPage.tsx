import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useLocation } from "react-router";
import { FormError } from "@/components/shared/FormError";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useReauth } from "@/hooks/reauth";
import { authorize, OAUTH_PARAMS, oauthNav, type Access, type AuthorizeResult } from "@/hooks/ai";
import { roleLabel } from "@/lib/api-types";
import { ApiError } from "@/lib/api";
import { APP_NAME } from "@/lib/constants";
import { Section } from "@/pages/admin/common";

/**
 * The OAuth authorization endpoint (D161). The person is already signed in (ProtectedLayout sends
 * them through login and MFA first). They choose labs and access; the server re-checks
 * everything and answers with the redirect back to the app.
 */
export function OAuthConsentPage() {
  const { search } = useLocation();
  const qs = new URLSearchParams(search);
  const query = Object.fromEntries(OAUTH_PARAMS.map((k) => [k, qs.get(k) ?? ""]));
  const check = useQuery({
    queryKey: ["oauth-check", search],
    queryFn: () => authorize({ ...query, decision: "check" }),
    retry: false,
  });
  const reauth = useReauth(); // D194: approving needs a recent sign-in or password check
  const decide = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      reauth.run(() => authorize({ ...query, ...body })),
    onSuccess: (r) => r.redirect && oauthNav.go(r.redirect),
  });
  const [labs, setLabs] = useState<string[] | null>(null);
  const [access, setAccess] = useState<Access | null>(null);

  if (check.isLoading)
    return (
      <div className="grid gap-3 p-8" aria-busy="true" aria-label="Loading">
        <Skeleton className="h-6 w-48" />
      </div>
    );
  if (check.error || !check.data?.client) {
    const body = check.error instanceof ApiError ? (check.error.body as AuthorizeResult) : null;
    return (
      <>
        <PageHeader title="This connection request isn't valid" />
        <p className="max-w-xl text-sm text-muted-foreground">
          {body?.error_description ?? "The app sent an incomplete or unknown request."} Start the
          connection again from your AI app.
        </p>
        {body?.redirect && (
          <Button className="mt-4 w-fit" onClick={() => oauthNav.go(body.redirect!)}>
            Return to the app
          </Button>
        )}
      </>
    );
  }

  const { client, labs: myLabs = [], requested_access } = check.data;
  // D198: the safest choice is the default. One lab and read only; anything wider is a tick.
  const chosen = labs ?? (myLabs[0] ? [String(myLabs[0].id)] : []);
  const level: Access = access ?? "read";
  const canWrite = requested_access === "write";
  const decideError = decide.error instanceof ApiError ? decide.error.message : undefined;

  return (
    <>
      <PageHeader
        title={`Connect ${client.name} to ${APP_NAME}?`}
        description="The app will act as you: it sees only what you can see, in the labs you choose, and your role still decides what it may change."
      />
      <div className="grid max-w-2xl gap-6">
        <Section title="The app">
          <p className="text-sm">
            <strong>{client.name}</strong>{" "}
            {client.verified_host && (
              <span className="text-muted-foreground">
                (identity published by {client.verified_host})
              </span>
            )}
          </p>
          {!client.verified_host && (
            <p role="alert" className="text-sm font-medium text-warning-text">
              Unverified app: the name &ldquo;{client.name}&rdquo; was chosen by the app itself and
              we cannot check it. Only continue if you started this connection yourself.
            </p>
          )}
          <p className="text-sm">
            After you decide, you will be sent to <strong>{client.redirect_host}</strong>.
          </p>
          {client.loopback && (
            <p role="alert" className="text-sm font-medium text-warning-text">
              This app runs on a computer, not a website. Only allow it if you started this
              connection yourself just now (for example from Claude Code).
            </p>
          )}
        </Section>
        <Section
          title="Labs"
          description="The app can read only the labs you tick. Start with one."
        >
          <fieldset className="grid gap-1">
            <legend className="sr-only">Labs to share</legend>
            {myLabs.map((lab) => (
              <label key={String(lab.id)} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={chosen.includes(String(lab.id))}
                  onChange={(e) =>
                    setLabs(
                      e.target.checked
                        ? [...chosen, String(lab.id)]
                        : chosen.filter((id) => id !== String(lab.id)),
                    )
                  }
                />
                {lab.name} <span className="text-muted-foreground">({roleLabel(lab.role)})</span>
              </label>
            ))}
          </fieldset>
          {chosen.length > 1 && (
            <p role="alert" className="text-sm font-medium text-warning-text">
              You chose {chosen.length} labs. The app can read all of them in one conversation, so
              text in one lab can end up beside another lab&apos;s records.
            </p>
          )}
        </Section>
        <Section title="Access">
          <fieldset className="grid gap-2">
            <legend className="sr-only">Access level</legend>
            <label className="flex items-start gap-2 text-sm">
              <input
                type="radio"
                name="access"
                checked={level === "read"}
                onChange={() => setAccess("read")}
              />
              <span>
                <strong>Read only</strong>: projects, tasks, documents, lineage, ethics approvals,
                funding and your notifications.
              </span>
            </label>
            <label className="flex items-start gap-2 text-sm">
              <input
                type="radio"
                name="access"
                disabled={!canWrite}
                checked={level === "write"}
                onChange={() => setAccess("write")}
              />
              <span>
                <strong>Read and write</strong>: also create tasks, post task updates and draft
                decisions, where your role allows.
                {!canWrite && " The app did not ask for this."}
              </span>
            </label>
          </fieldset>
          {level === "write" && (
            <p role="alert" className="text-sm font-medium text-warning-text">
              The app will be able to add records as you. Text it reads in your lab (a task note or
              a document from anyone) may try to steer it, so check what it does. Choose read only
              if you are unsure.
            </p>
          )}
        </Section>
        <FormError message={decideError} />
        <div className="flex gap-3">
          <Button
            disabled={chosen.length === 0 || decide.isPending}
            onClick={() => decide.mutate({ decision: "approve", labs: chosen, access: level })}
          >
            Allow
          </Button>
          <Button
            variant="outline"
            disabled={decide.isPending}
            onClick={() => decide.mutate({ decision: "deny" })}
          >
            Deny
          </Button>
        </div>
        <p className="text-sm text-muted-foreground">
          You can disconnect it at any time in Settings, under Connected AI apps.
        </p>
      </div>
      {reauth.dialog}
    </>
  );
}
