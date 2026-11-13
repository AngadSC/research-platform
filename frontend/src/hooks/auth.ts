import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, getCookie, rawRequest, SESSION_URL, toApiError } from "@/lib/api";
import type { AuthEnvelope, RecoveryCodes, TotpAuthenticator } from "@/lib/api-types";

const BASE = "/_allauth/browser/v1";

export interface AuthResult {
  authenticated: boolean;
  /** Ids of flows still waiting on the user, e.g. "mfa_authenticate" or "verify_email". */
  pending: string[];
  env: AuthEnvelope;
}

/** allauth answers 200 when done and 401 with a flow list when more steps are needed. Anything else is an error. */
async function allauth(path: string, method = "GET", body?: unknown): Promise<AuthResult> {
  const res = await rawRequest(BASE + path, { method, body });
  if (res.status !== 200 && res.status !== 401) throw toApiError(res.status, res.body);
  const env = (res.body ?? { status: res.status }) as AuthEnvelope;
  return {
    authenticated: res.status === 200 && env.meta?.is_authenticated !== false,
    pending: (env.data?.flows ?? []).filter((f) => f.is_pending).map((f) => f.id),
    env,
  };
}

const SESSION_KEY = ["session"];

/** Session state for the whole app. Backed by one shared query, so every caller sees the same answer. */
export function useAuth() {
  const q = useQuery({
    queryKey: SESSION_KEY,
    queryFn: () => allauth("/auth/session"),
    staleTime: 60_000,
    // While the server is briefly down (a deploy), keep trying instead of treating it as a logout.
    refetchInterval: (query) => (query.state.status === "error" ? 5000 : false),
  });
  // A 4xx answer means "not signed in". A 5xx or no answer at all (status 0) says nothing about that.
  const unavailable =
    q.isError &&
    !q.data &&
    !(q.error instanceof ApiError && q.error.status >= 400 && q.error.status < 500);
  return {
    unavailable,
    retry: () => void q.refetch(),
    isLoading: q.isLoading,
    isAuthenticated: q.data?.authenticated ?? false,
    email: q.data?.env.data?.user?.email,
    hasUsablePassword: q.data?.env.data?.user?.has_usable_password ?? false,
  };
}

function useSessionMutation<V>(fn: (v: V) => Promise<AuthResult>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (r) => {
      if (r.authenticated) qc.setQueryData(SESSION_KEY, r);
    },
  });
}

export const useLogin = () =>
  useSessionMutation((v: { email: string; password: string }) => allauth("/auth/login", "POST", v));
export const useSignup = () =>
  useSessionMutation((v: { email: string; password: string }) =>
    allauth("/auth/signup", "POST", v),
  );
export const useVerifyEmail = () =>
  useSessionMutation((key: string) => allauth("/auth/email/verify", "POST", { key }));
export const useMfaAuthenticate = () =>
  useSessionMutation((code: string) => allauth("/auth/2fa/authenticate", "POST", { code }));

/** A full page load back to the signed-out home page, so nothing of the session stays in memory. */
export function useLogout() {
  return useMutation({
    mutationFn: () => allauth("/auth/session", "DELETE"),
    onSuccess: () => window.location.assign("/"),
  });
}

// ---- Two-step verification (TOTP) and recovery codes ----

export interface TotpState {
  enabled: boolean;
  /** Set when not yet enabled: the secret to put in an authenticator app. */
  secret?: string;
}

const TOTP_KEY = ["totp"];
const CODES_KEY = ["recovery-codes"];

export function useTotp() {
  return useQuery({
    queryKey: TOTP_KEY,
    queryFn: async (): Promise<TotpState> => {
      const r = await rawRequest(`${BASE}/account/authenticators/totp`);
      if (r.status === 200) return { enabled: !!(r.body as { data?: TotpAuthenticator }).data };
      if (r.status === 404)
        return { enabled: false, secret: (r.body as AuthEnvelope).meta?.secret };
      throw toApiError(r.status, r.body);
    },
  });
}

export function useRecoveryCodes(enabled: boolean) {
  return useQuery({
    queryKey: CODES_KEY,
    enabled,
    queryFn: async (): Promise<RecoveryCodes | null> => {
      const r = await rawRequest(`${BASE}/account/authenticators/recovery_codes`);
      if (r.status === 404) return null;
      if (r.status !== 200) throw toApiError(r.status, r.body);
      return (r.body as { data: RecoveryCodes }).data;
    },
  });
}

function useSecurityMutation<V>(fn: (v: V) => Promise<AuthResult>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: V) => {
      const r = await fn(v);
      // A signed-in user only gets 401 here when a recent password/code check is needed (D74).
      if (r.env.status === 401) throw toApiError(401, r.env);
      return r;
    },
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: TOTP_KEY }),
        qc.invalidateQueries({ queryKey: CODES_KEY }),
      ]),
  });
}
export const useActivateTotp = () =>
  useSecurityMutation((code: string) => allauth("/account/authenticators/totp", "POST", { code }));
export const useDeactivateTotp = () =>
  useSecurityMutation(() => allauth("/account/authenticators/totp", "DELETE"));
export const useRegenerateRecoveryCodes = () =>
  useSecurityMutation(() => allauth("/account/authenticators/recovery_codes", "POST"));

// ---- Google sign-in, connected accounts and email addresses ----

export interface ProviderInfo {
  id: string;
  name: string;
}
export interface ProviderAccount {
  uid: string;
  display: string;
  provider: ProviderInfo;
}
export interface EmailAddress {
  email: string;
  primary: boolean;
  verified: boolean;
}

/** Providers the server has configured (empty when Google env vars are unset). */
export function useProviders() {
  return useQuery({
    queryKey: ["auth-config"],
    staleTime: 5 * 60_000,
    queryFn: async (): Promise<ProviderInfo[]> => {
      // The provider form posts natively, so the CSRF cookie must exist before it renders.
      if (!getCookie("csrftoken"))
        await fetch(SESSION_URL, { headers: { Accept: "application/json" } });
      const r = await rawRequest(`${BASE}/config`);
      if (r.status !== 200) return [];
      const b = r.body as { data?: { socialaccount?: { providers?: ProviderInfo[] } } };
      return b.data?.socialaccount?.providers ?? [];
    },
  });
}

/** Re-reads the session after returning from a provider; always hits the server. */
export function useRefreshSession() {
  const qc = useQueryClient();
  return () =>
    qc.fetchQuery({
      queryKey: SESSION_KEY,
      queryFn: () => allauth("/auth/session"),
      staleTime: 0,
    });
}

const ACCOUNTS_KEY = ["provider-accounts"];
const EMAILS_KEY = ["emails"];
const listData = async <T>(path: string, method = "GET", body?: unknown) =>
  (await api<{ data: T[] }>(BASE + path, { method, body })).data;

export const useProviderAccounts = () =>
  useQuery({
    queryKey: ACCOUNTS_KEY,
    queryFn: () => listData<ProviderAccount>("/account/providers"),
  });

export function useDisconnectProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (a: ProviderAccount) =>
      listData<ProviderAccount>("/account/providers", "DELETE", {
        provider: a.provider.id,
        account: a.uid,
      }),
    onSuccess: (d) => qc.setQueryData(ACCOUNTS_KEY, d),
  });
}

export const useEmails = () =>
  useQuery({ queryKey: EMAILS_KEY, queryFn: () => listData<EmailAddress>("/account/email") });

export function useEmailAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      op,
      email,
    }: {
      op: "add" | "remove" | "primary" | "resend";
      email: string;
    }) => {
      if (op === "resend") {
        await api(`${BASE}/account/email`, { method: "PUT", body: { email } });
        return null;
      }
      const method = { add: "POST", remove: "DELETE", primary: "PATCH" }[op];
      const body = op === "primary" ? { email, primary: true } : { email };
      return listData<EmailAddress>("/account/email", method, body);
    },
    onSuccess: (d) => d && qc.setQueryData(EMAILS_KEY, d),
  });
}

// ---- Reauthentication (D74) ----

export class ReauthCancelled extends Error {}

export interface ReauthFlows {
  password: boolean;
  mfa: boolean;
}

/** allauth answers a sensitive action with 401 and the flows that would satisfy it; null for any other error. */
export function reauthFlows(e: unknown): ReauthFlows | null {
  if (!(e instanceof ApiError) || e.status !== 401) return null;
  const flows = (e.body as AuthEnvelope | null)?.data?.flows ?? [];
  const ids = flows.map((f) => f.id);
  const out = { password: ids.includes("reauthenticate"), mfa: ids.includes("mfa_reauthenticate") };
  return out.password || out.mfa ? out : null;
}

/** Proves the password and/or a TOTP code (whichever the account has) so the action can be retried. */
export async function reauthenticate(
  flows: ReauthFlows,
  v: { password?: string; code?: string },
): Promise<void> {
  if (flows.password)
    await api(`${BASE}/auth/reauthenticate`, { method: "POST", body: { password: v.password } });
  if (flows.mfa)
    await api(`${BASE}/auth/2fa/reauthenticate`, { method: "POST", body: { code: v.code } });
}
