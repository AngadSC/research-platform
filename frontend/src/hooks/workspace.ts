import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  AuditPage,
  Invite,
  InvitePreview,
  Lab,
  Membership,
  Role,
  User,
} from "@/lib/api-types";

const j = (body: unknown) => ({ body });

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => api<User>("/api/me/") });
}
export function useUpdateMe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { display_name: string }) =>
      api<User>("/api/me/", { method: "PATCH", ...j(v) }),
    onSuccess: (u) => qc.setQueryData(["me"], u),
  });
}

export function useLabs() {
  return useQuery({ queryKey: ["labs"], queryFn: () => api<Lab[]>("/api/labs/") });
}
export function useLab(labId: string | undefined) {
  return useQuery({
    queryKey: ["labs", labId],
    queryFn: () => api<Lab>(`/api/labs/${labId}/`),
    enabled: !!labId,
  });
}
export function useCreateLab() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: {
      name: string;
      institution_name?: string;
      address?: string;
      website?: string;
    }) =>
      api<Lab>("/api/labs/", { method: "POST", ...j(v) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labs"] }),
  });
}
export function useUpdateLab(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { name: string }) =>
      api<Lab>(`/api/labs/${labId}/`, { method: "PATCH", ...j(v) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labs"] }),
  });
}

export function useMembers(labId: string) {
  return useQuery({
    queryKey: ["labs", labId, "members"],
    queryFn: () => api<Membership[]>(`/api/labs/${labId}/members/`),
  });
}
export function useUpdateMember(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: string; role: Role }) =>
      api<Membership>(`/api/labs/${labId}/members/${v.id}/`, {
        method: "PATCH",
        ...j({ role: v.role }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labs", labId] }),
  });
}
export function useRemoveMember(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api(`/api/labs/${labId}/members/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labs", labId] }),
  });
}

export function useInvites(labId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["labs", labId, "invites"],
    queryFn: () => api<Invite[]>(`/api/labs/${labId}/invites/`),
    enabled,
  });
}
export function useCreateInvite(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { email: string; role: Role }) =>
      api<Invite>(`/api/labs/${labId}/invites/`, { method: "POST", ...j(v) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labs", labId, "invites"] }),
  });
}
export function useRevokeInvite(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api(`/api/labs/${labId}/invites/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labs", labId, "invites"] }),
  });
}

export function useInvitePreview(token: string) {
  return useQuery({
    queryKey: ["invite-preview", token],
    queryFn: () => api<InvitePreview>("/api/invites/preview/", { method: "POST", ...j({ token }) }),
    retry: false,
  });
}
export function useAcceptInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (token: string) =>
      api<Lab>("/api/invites/accept/", { method: "POST", ...j({ token }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labs"] }),
  });
}

export interface AuditFilters {
  action?: string;
  actor?: string;
  date_from?: string;
  date_to?: string;
}
/** Cursor-paginated audit log; `next` is a full URL, so only its cursor is kept. */
export function useAuditEvents(labId: string, filters: AuditFilters, enabled: boolean) {
  return useInfiniteQuery({
    queryKey: ["labs", labId, "audit", filters],
    queryFn: ({ pageParam }) => {
      const qs = new URLSearchParams(Object.entries(filters).filter(([, v]) => v));
      if (pageParam) qs.set("cursor", pageParam);
      return api<AuditPage>(`/api/labs/${labId}/audit-events/?${qs}`);
    },
    initialPageParam: "",
    getNextPageParam: (last) =>
      last.next
        ? (new URL(last.next, window.location.origin).searchParams.get("cursor") ?? undefined)
        : undefined,
    enabled,
    retry: false,
  });
}
