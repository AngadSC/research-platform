import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { ProviderButton, RETURN_KEY } from "@/components/auth/ProviderButton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  useAuth,
  useLogin,
  useMfaAuthenticate,
  useRefreshSession,
  useSignup,
  useVerifyEmail,
  type AuthResult,
} from "@/hooks/auth";
import { formErrors, safeNext, type FormErrors } from "@/lib/forms";

const FIELDS = ["email", "password", "code"];
const NO_ERRORS: FormErrors = { fields: {} };

function Heading({ title, children }: { title: string; children?: string }) {
  return (
    <header className="mb-6">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {children && <p className="mt-1 text-sm text-muted-foreground">{children}</p>}
    </header>
  );
}

function useNext() {
  const [params] = useSearchParams();
  const raw = params.get("next");
  return { next: safeNext(raw), raw };
}

const withNext = (path: string, raw: string | null) =>
  raw ? `${path}?next=${encodeURIComponent(raw)}` : path;

/** Shared by login and signup: email and password, then route on what allauth says is pending. */
function CredentialsForm({
  submitLabel,
  autoComplete,
  run,
  onPending,
  footer,
}: {
  submitLabel: string;
  autoComplete: string;
  run: (v: { email: string; password: string }) => Promise<AuthResult>;
  onPending: (r: AuthResult, email: string) => void;
  footer: React.ReactNode;
}) {
  const [errors, setErrors] = useState<FormErrors>(NO_ERRORS);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const email = String(f.get("email") ?? "").trim();
    const password = String(f.get("password") ?? "");
    const fields: Record<string, string> = {};
    if (!email) fields.email = "Enter your email address";
    if (!password) fields.password = "Enter your password";
    if (Object.keys(fields).length) return setErrors({ fields });
    setErrors(NO_ERRORS);
    setBusy(true);
    try {
      onPending(await run({ email, password }), email);
    } catch (err) {
      setErrors(formErrors(err, FIELDS));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-4">
      <form onSubmit={submit} noValidate className="grid gap-4">
        <FormField label="Email" error={errors.fields.email}>
          {(p) => <Input {...p} name="email" type="email" autoComplete="email" />}
        </FormField>
        <FormField label="Password" error={errors.fields.password}>
          {(p) => <Input {...p} name="password" type="password" autoComplete={autoComplete} />}
        </FormField>
        <FormError message={errors.form} />
        <Button type="submit" disabled={busy}>
          {submitLabel}
        </Button>
      </form>
      <ProviderButton process="login" label="Continue with Google" />
      <p className="text-sm text-muted-foreground">{footer}</p>
    </div>
  );
}

function CodeForm({ next }: { next: string }) {
  const mfa = useMfaAuthenticate();
  const navigate = useNavigate();
  const [errors, setErrors] = useState<FormErrors>(NO_ERRORS);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const code = String(new FormData(e.currentTarget).get("code") ?? "").trim();
    if (!code) return setErrors({ fields: { code: "Enter the code from your authenticator app" } });
    setErrors(NO_ERRORS);
    try {
      await mfa.mutateAsync(code);
      void navigate(next, { replace: true });
    } catch (err) {
      setErrors(formErrors(err, FIELDS));
    }
  }

  return (
    <>
      <Heading title="Two-step verification">
        Enter the code from your authenticator app to finish signing in.
      </Heading>
      <form onSubmit={submit} noValidate className="grid gap-4">
        <FormField
          label="Authentication code"
          hint="Lost your phone? Use one of your recovery codes instead."
          error={errors.fields.code}
        >
          {(p) => <Input {...p} name="code" autoComplete="one-time-code" inputMode="text" />}
        </FormField>
        <FormError message={errors.form} />
        <Button type="submit" disabled={mfa.isPending}>
          Verify
        </Button>
      </form>
    </>
  );
}

export function LoginPage() {
  const { isAuthenticated } = useAuth();
  const { next, raw } = useNext();
  const navigate = useNavigate();
  const login = useLogin();
  const [params] = useSearchParams();
  const [needsCode, setNeedsCode] = useState(params.get("mfa") === "1");

  if (isAuthenticated) return <Navigate to={next} replace />;
  if (needsCode) return <CodeForm next={next} />;

  return (
    <>
      <Heading title="Sign in">Welcome back. Sign in to see your labs and projects.</Heading>
      <CredentialsForm
        submitLabel="Sign in"
        autoComplete="current-password"
        run={(v) => login.mutateAsync(v)}
        onPending={(r, email) => {
          if (r.pending.includes("mfa_authenticate")) setNeedsCode(true);
          else if (r.pending.includes("verify_email"))
            void navigate(
              `${withNext("/check-email", raw)}${raw ? "&" : "?"}email=${encodeURIComponent(email)}`,
            );
        }}
        footer={
          <>
            New here?{" "}
            <Link className="font-medium text-primary underline" to={withNext("/signup", raw)}>
              Create an account
            </Link>
          </>
        }
      />
    </>
  );
}

export function SignupPage() {
  const { isAuthenticated } = useAuth();
  const { next, raw } = useNext();
  const navigate = useNavigate();
  const signup = useSignup();

  if (isAuthenticated) return <Navigate to={next} replace />;

  return (
    <>
      <Heading title="Create your account">
        You will get an email to confirm your address before you can sign in.
      </Heading>
      <CredentialsForm
        submitLabel="Create account"
        autoComplete="new-password"
        run={(v) => signup.mutateAsync(v)}
        onPending={(r, email) => {
          if (!r.authenticated)
            void navigate(
              `${withNext("/check-email", raw)}${raw ? "&" : "?"}email=${encodeURIComponent(email)}`,
            );
        }}
        footer={
          <>
            Already have an account?{" "}
            <Link className="font-medium text-primary underline" to={withNext("/login", raw)}>
              Sign in
            </Link>
          </>
        }
      />
    </>
  );
}

export function CheckEmailPage() {
  const [params] = useSearchParams();
  const email = params.get("email");
  const raw = params.get("next");
  return (
    <>
      <Heading title="Check your email" />
      <p className="text-sm">
        We sent a confirmation link
        {email ? (
          <>
            {" "}
            to <strong>{email}</strong>
          </>
        ) : (
          ""
        )}
        . Open it to confirm your address, then sign in.
      </p>
      <p className="mt-4 text-sm text-muted-foreground">
        Nothing there? Check your spam folder.{" "}
        <Link className="font-medium text-primary underline" to={withNext("/login", raw)}>
          Go to sign in
        </Link>
      </p>
    </>
  );
}

export function VerifyEmailPage() {
  const { key = "" } = useParams();
  const verify = useVerifyEmail();
  const [error, setError] = useState<string>();

  // A button, not an automatic request: mail scanners that open links must not use up the key.
  async function confirm() {
    setError(undefined);
    try {
      await verify.mutateAsync(key);
    } catch (err) {
      setError(formErrors(err, []).form);
    }
  }

  if (verify.isSuccess)
    return (
      <>
        <Heading title="Email confirmed" />
        <p className="mb-4 text-sm">Thanks. Your email address is confirmed.</p>
        <Button asChild>
          <Link to={verify.data.authenticated ? "/" : "/login"}>
            {verify.data.authenticated ? "Continue" : "Sign in"}
          </Link>
        </Button>
      </>
    );

  return (
    <>
      <Heading title="Confirm your email">Confirm that this is your email address.</Heading>
      <div className="grid gap-4">
        <FormError message={error} />
        <Button onClick={() => void confirm()} disabled={verify.isPending}>
          Confirm email address
        </Button>
      </div>
    </>
  );
}

/** Where the browser lands after Google. allauth adds ?error= on failure; otherwise the session says what is next. */
export function ProviderCallbackPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const refresh = useRefreshSession();
  const failed = params.has("error");
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    if (failed) return;
    const back = sessionStorage.getItem(RETURN_KEY);
    sessionStorage.removeItem(RETURN_KEY);
    refresh().then(
      (r) => {
        if (r.pending.includes("mfa_authenticate"))
          void navigate("/login?mfa=1", { replace: true });
        else if (r.pending.includes("verify_email"))
          void navigate("/check-email", { replace: true });
        else void navigate(r.authenticated ? (back ?? "/") : "/login", { replace: true });
      },
      () => setOffline(true),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on arrival
  }, []);

  if (failed || offline)
    return (
      <>
        <Heading title="Google sign-in did not finish" />
        <p className="text-sm">
          {offline
            ? "We couldn't reach the server. Check your connection and try again."
            : "Google did not let us sign you in. You may have cancelled, or this Google account cannot be used. Try again, or sign in with your email and password."}
        </p>
        <Button asChild className="mt-4">
          <Link to="/login">Back to sign in</Link>
        </Button>
      </>
    );
  return <p className="text-sm text-muted-foreground">Finishing sign-in...</p>;
}
