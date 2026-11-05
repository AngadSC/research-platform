import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-schema";

type S = components["schemas"];
export type KeyStatus = S["KeyStatus"];
export type AssistantConfig = S["AssistantConfig"];
export type ProviderConfig = S["ProviderConfig"];
export type Conversation = S["Conversation"];
export type ConversationDetail = S["ConversationDetail"];
export type TimelineItem = S["TimelineItem"];
export type PendingCall = S["PendingCall"];
export type AiPolicy = S["AiPolicyEnum"];
export type Provider = S["ProviderEnum"];

const KEYS = ["ai-keys"];
const lab = (labId: string) => ["assistant", labId];

// ---- a person's own provider keys (Settings > AI)

export function useAiKeys() {
  return useQuery({ queryKey: KEYS, queryFn: () => api<KeyStatus[]>("/api/ai/keys/") });
}

export function useSaveAiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ provider, apiKey }: { provider: Provider; apiKey: string }) =>
      api<KeyStatus>(`/api/ai/keys/${provider}/`, { method: "PUT", body: { api_key: apiKey } }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEYS });
      void qc.invalidateQueries({ queryKey: ["assistant"] });
    },
  });
}

export function useRemoveAiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (provider: Provider) => api(`/api/ai/keys/${provider}/`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEYS });
      void qc.invalidateQueries({ queryKey: ["assistant"] });
    },
  });
}

export function useSetRefusalFallback() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (refusal_fallback: boolean) =>
      api<KeyStatus>("/api/ai/keys/anthropic/", { method: "PATCH", body: { refusal_fallback } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEYS }),
  });
}

// ---- the lab's AI policy (D188)

export function useLabAiPolicy(labId: string) {
  return useQuery({
    queryKey: [...lab(labId), "policy"],
    queryFn: () => api<{ ai_policy: AiPolicy }>(`/api/labs/${labId}/ai-policy/`),
  });
}

export function useSetLabAiPolicy(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ai_policy: AiPolicy) =>
      api<{ ai_policy: AiPolicy }>(`/api/labs/${labId}/ai-policy/`, {
        method: "PATCH",
        body: { ai_policy },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: lab(labId) }),
  });
}

// ---- the assistant panel

export function useAssistantConfig(labId: string, enabled: boolean) {
  return useQuery({
    queryKey: [...lab(labId), "config"],
    queryFn: () => api<AssistantConfig>(`/api/labs/${labId}/assistant/config/`),
    enabled,
  });
}

export function useConversations(labId: string, enabled: boolean) {
  return useQuery({
    queryKey: [...lab(labId), "conversations"],
    queryFn: () => api<Conversation[]>(`/api/labs/${labId}/assistant/conversations/`),
    enabled,
  });
}

export const conversationKey = (labId: string, id: string) => [...lab(labId), "conversation", id];

export function useConversation(labId: string, id: string | null) {
  return useQuery({
    queryKey: conversationKey(labId, id ?? ""),
    queryFn: () => api<ConversationDetail>(`/api/labs/${labId}/assistant/conversations/${id}/`),
    enabled: !!id,
  });
}

export function useCreateConversation(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { provider: Provider; model: string; project?: string }) =>
      api<Conversation>(`/api/labs/${labId}/assistant/conversations/`, { method: "POST", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...lab(labId), "conversations"] }),
  });
}

export function useDeleteConversation(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api(`/api/labs/${labId}/assistant/conversations/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: lab(labId) }),
  });
}
