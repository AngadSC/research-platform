import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-schema";

type S = components["schemas"];
export type AiGrant = S["Grant"];
export type LabAiGrant = S["LabGrant"];
export type PatCreated = S["PatCreated"];
export type AuthorizeResult = S["AuthorizeResult"];
export type Access = "read" | "write";

/** The OAuth query parameters the MCP client put on /oauth/authorize, passed through as-is. */
export const OAUTH_PARAMS = [
  "response_type",
  "client_id",
  "redirect_uri",
  "code_challenge",
  "code_challenge_method",
  "state",
  "scope",
  "resource",
] as const;

const KEY = ["ai-grants"];

export function useAiGrants() {
  return useQuery({ queryKey: KEY, queryFn: () => api<AiGrant[]>("/api/ai/grants/") });
}

export function useCreatePat() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; labs: string[]; access: Access; expires_in_days: number }) =>
      api<PatCreated>("/api/ai/grants/", { method: "POST", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useRevokeGrant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api(`/api/ai/grants/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useLabAiGrants(labId: string) {
  return useQuery({
    queryKey: ["labs", labId, "ai-grants"],
    queryFn: () => api<LabAiGrant[]>(`/api/labs/${labId}/ai-grants/`),
  });
}

export function useRemoveLabGrant(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api(`/api/labs/${labId}/ai-grants/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labs", labId, "ai-grants"] }),
  });
}

export function authorize(body: Record<string, unknown>) {
  return api<AuthorizeResult>("/api/oauth/authorize/", { method: "POST", body });
}

/** Leaving for the AI app's redirect URI; a seam so tests can watch it. */
export const oauthNav = { go: (url: string) => window.location.assign(url) };

/** The MCP endpoint people paste into Claude or ChatGPT: this site's origin + /mcp. */
export const mcpUrl = () => `${window.location.origin}/mcp`;
