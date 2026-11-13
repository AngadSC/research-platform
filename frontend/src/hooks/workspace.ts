import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { AuditPage, Invite, InvitePreview, Lab, Me, Membership, Role } from "@/lib/api-types";

const j = (body: unknown) => ({ body });

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/api/me/") });
}
export function useUpdateMe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { display_name?: string; pronouns?: string; bio?: string }) =>
      api<Me>("/api/me/", { method: "PATCH", ...j(v) }),
    onSuccess: (u) => qc.setQueryData(["me"], u),
  });
}

/** Sets (a PNG blob) or removes (null) your profile picture. People lists show it too. */
export function useSetAvatar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (picture: Blob | null) => {
      if (picture === null) {
        await api("/api/me/avatar/", { method: "DELETE" });
        return api<Me>("/api/me/");
      }
      const form = new FormData();
      form.append("file", picture, "avatar.png");
      return api<Me>("/api/me/avatar/", { method: "PUT", body: form });
    },
    onSuccess: (me) => {
      qc.setQueryData(["me"], me);
      void qc.invalidateQueries({ queryKey: ["labs"] }); // member lists carry the picture
    },
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
    }) => api<Lab>("/api/labs/", { method: "POST", ...j(v) }),
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
export function useUpdateInvite(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: string; role: Role }) =>
      api<Invite>(`/api/labs/${labId}/invites/${v.id}/`, {
        method: "PATCH",
        ...j({ role: v.role }),
      }),
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
  /** Leave out views, downloads and other reads. */
  changes_only?: string;
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
