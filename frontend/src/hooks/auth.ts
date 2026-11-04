import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { rawRequest, toApiError } from "@/lib/api";
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
  });
  return {
    isLoading: q.isLoading,
    isAuthenticated: q.data?.authenticated ?? false,
    email: q.data?.env.data?.user?.email,
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

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => allauth("/auth/session", "DELETE"),
    onSuccess: () => {
      qc.clear();
      qc.setQueryData(SESSION_KEY, { authenticated: false, pending: [], env: { status: 401 } });
    },
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
    mutationFn: fn,
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
