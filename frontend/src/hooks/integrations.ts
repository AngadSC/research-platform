import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  ConnectedAccount,
  ConnectOutput,
  ExternalLink,
  ExternalLinkInput,
  IntegrationProvider,
  ItemSearchResult,
  PickerToken,
} from "@/lib/api-types";

const base = (labId: string) => `/api/labs/${labId}`;
const root = (labId: string) => ["labs", labId, "integrations"] as const;

export function useProviders(labId: string) {
  return useQuery({
    queryKey: [...root(labId), "providers"],
    queryFn: () => api<IntegrationProvider[]>(`${base(labId)}/integrations/providers/`),
    enabled: !!labId,
  });
}

/** Everyone's connections when `all` (the server still returns only your own to people without
 * the right to see more). */
export function useAccounts(labId: string, all: boolean, enabled = true) {
  return useQuery({
    queryKey: [...root(labId), "accounts", all],
    queryFn: () =>
      api<ConnectedAccount[]>(`${base(labId)}/integrations/accounts/${all ? "?all=true" : ""}`),
    enabled: !!labId && enabled,
  });
}

/** oauth2: asks for the consent URL and sends the browser there. api_key: `body` carries the
 * key (and secret, instance URL); the account is stored and the lists refresh. */
export function useConnect(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { provider: string; body?: Record<string, string> }) =>
      api<ConnectOutput>(`${base(labId)}/integrations/${v.provider}/connect/`, {
        method: "POST",
        body: v.body ?? {},
      }),
    onSuccess: (r) => {
      if (r.authorization_url) window.location.assign(r.authorization_url);
      else void qc.invalidateQueries({ queryKey: root(labId) });
    },
  });
}

/** Disconnect your own account, or revoke someone else's (the server decides which). */
export function useDisconnect(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (accountId: string) =>
      api<ConnectedAccount>(`${base(labId)}/integrations/accounts/${accountId}/`, {
        method: "DELETE",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: root(labId) }),
  });
}

export function useExternalLinks(labId: string, projectId: string, enabled = true) {
  return useQuery({
    queryKey: [...root(labId), "links", projectId],
    queryFn: () => api<ExternalLink[]>(`${base(labId)}/projects/${projectId}/external-links/`),
    enabled: !!labId && !!projectId && enabled,
  });
}

export function useCreateExternalLink(labId: string, projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: ExternalLinkInput) =>
      api<ExternalLink>(`${base(labId)}/projects/${projectId}/external-links/`, {
        method: "POST",
        body: v,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...root(labId), "links", projectId] }),
  });
}

export function useRemoveExternalLink(labId: string, projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api(`${base(labId)}/external-links/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...root(labId), "links", projectId] }),
  });
}

/** The only call that returns an access token (D70). Used right before opening the Picker. */
export const fetchPickerToken = (labId: string) =>
  api<PickerToken>(`${base(labId)}/integrations/google/picker-token/`);

export function useCheckExternalLink(labId: string, projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api<ExternalLink>(`${base(labId)}/external-links/${id}/check/`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...root(labId), "links", projectId] }),
  });
}

export function useAcceptExternalChange(labId: string, projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api<ExternalLink>(`${base(labId)}/external-links/${id}/accept-change/`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...root(labId), "links", projectId] }),
  });
}

/** Candidates from a provider's search (D85). Empty `q` asks for recent items. A newer `q`
 * aborts the older request through the query's signal. */
export function useItemSearch(
  labId: string,
  projectId: string,
  provider: string,
  target: string,
  q: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: [...root(labId), "search", projectId, provider, target, q],
    queryFn: ({ signal }) =>
      api<ItemSearchResult[]>(
        `${base(labId)}/projects/${projectId}/integrations/${provider}/search/?q=${encodeURIComponent(q)}&target=${target}`,
        { signal },
      ),
    enabled: enabled && !!labId && !!projectId,
    staleTime: 0,
    gcTime: 0, // results are never kept (D85)
    retry: false,
  });
}
