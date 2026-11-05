import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  ConnectedAccount,
  ConnectOutput,
  ExternalLink,
  ExternalLinkInput,
  IntegrationProvider,
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

/** Asks the server for the provider's consent URL, then sends the browser there. */
export function useConnect(labId: string) {
  return useMutation({
    mutationFn: (provider: string) =>
      api<ConnectOutput>(`${base(labId)}/integrations/${provider}/connect/`, {
        method: "POST",
        body: {},
      }),
    onSuccess: (r) => window.location.assign(r.authorization_url),
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
