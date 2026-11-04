import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/hooks/auth";
import { useAcceptInvite, useInvitePreview } from "@/hooks/workspace";
import { roleLabel } from "@/lib/api-types";
import { ApiError } from "@/lib/api";
import { formErrors } from "@/lib/forms";

export function AcceptInvitePage() {
  const { token = "" } = useParams();
  const preview = useInvitePreview(token);
  const { isLoading: authLoading, isAuthenticated, email } = useAuth();
  const accept = useAcceptInvite();
  const navigate = useNavigate();
  const next = encodeURIComponent(`/invite/${token}`);

  if (preview.isLoading || authLoading)
    return (
      <div aria-busy="true" aria-label="Loading" className="grid gap-3">
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-full" />
      </div>
    );

  if (preview.error || !preview.data)
    return (
      <>
        <h1 className="mb-2 text-2xl font-semibold tracking-tight">
          This invitation can't be used
        </h1>
        <p className="text-sm text-muted-foreground">
          The link may have expired or been cancelled. Ask the person who invited you to send a new
          one.
        </p>
      </>
    );

  const { lab_name, role, email: invitedEmail } = preview.data;
  const wrongAccount =
    isAuthenticated && !!email && email.toLowerCase() !== invitedEmail.toLowerCase();

  return (
    <>
      <h1 className="mb-2 text-2xl font-semibold tracking-tight">Join {lab_name}</h1>
      <p className="mb-6 text-sm text-muted-foreground">
        You have been invited to join <strong>{lab_name}</strong> as {roleLabel(role)}. This
        invitation is for {invitedEmail}.
      </p>
      {isAuthenticated ? (
        <div className="grid gap-4">
          {wrongAccount && (
            <FormError
              message={`You are signed in as ${email}. Sign in with ${invitedEmail} to accept.`}
            />
          )}
          {accept.error && (
            <FormError
              message={
                accept.error instanceof ApiError && accept.error.status === 403
                  ? `Sign in with ${invitedEmail} (and confirm that address) to accept this invitation.`
                  : formErrors(accept.error, []).form
              }
            />
          )}
          <Button
            disabled={accept.isPending || wrongAccount}
            onClick={() =>
              accept.mutate(token, {
                onSuccess: (lab) => {
                  toast.success(`You joined ${lab.name}`);
                  void navigate(`/labs/${lab.id}`);
                },
              })
            }
          >
            Join {lab_name}
          </Button>
        </div>
      ) : (
        <div className="grid gap-3">
          <Button asChild>
            <Link to={`/login?next=${next}`}>Sign in to accept</Link>
          </Button>
          <Button asChild variant="outline">
            <Link to={`/signup?next=${next}`}>Create an account</Link>
          </Button>
          <p className="text-xs text-muted-foreground">
            Use {invitedEmail} so the invitation matches your account.
          </p>
        </div>
      )}
    </>
  );
}
