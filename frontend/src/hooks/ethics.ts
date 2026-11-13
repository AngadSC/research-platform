import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, upload } from "@/lib/api";
import type {
  AppNotification,
  Attachment,
  EthicsApproval,
  EthicsApprovalInput,
  RetentionItem,
} from "@/lib/api-types";

const base = (labId: string) => `/api/labs/${labId}`;
const root = (labId: string) => ["labs", labId, "ethics"] as const;

export function useApprovals(labId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: [...root(labId ?? "")],
    queryFn: () => api<EthicsApproval[]>(`${base(labId!)}/ethics-approvals/`),
    enabled: !!labId && enabled,
  });
}

export function useApproval(labId: string | undefined, id: string | undefined) {
  return useQuery({
    queryKey: [...root(labId ?? ""), id],
    queryFn: () => api<EthicsApproval>(`${base(labId!)}/ethics-approvals/${id}/`),
    enabled: !!labId && !!id,
  });
}

export function useSaveApproval(labId: string, id?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: Partial<EthicsApprovalInput>) =>
      api<EthicsApproval>(`${base(labId)}/ethics-approvals/${id ? `${id}/` : ""}`, {
        method: id ? "PATCH" : "POST",
        body: v,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: root(labId) }),
  });
}

export function useDeleteApproval(labId: string, id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api(`${base(labId)}/ethics-approvals/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: root(labId) }),
  });
}

export function useApprovalUpload(labId: string, id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { file: File; onProgress?: (f: number) => void }) => {
      const form = new FormData();
      form.append("file", v.file);
      form.append("acknowledged_notice", "true");
      return upload<Attachment>(
        `${base(labId)}/ethics-approvals/${id}/attachments/`,
        form,
        v.onProgress,
      );
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: root(labId) }),
  });
}

const nKey = (labId: string) => ["labs", labId, "notifications"] as const;

/** Polls every minute and on window focus. */
export function useNotifications(labId: string | undefined) {
  return useQuery({
    queryKey: [...nKey(labId ?? "")],
    queryFn: () => api<AppNotification[]>(`${base(labId!)}/notifications/`),
    enabled: !!labId,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });
}

export function useMarkRead(labId: string) {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: nKey(labId) });
  const one = useMutation({
    mutationFn: (id: string) => api(`${base(labId)}/notifications/${id}/read/`, { method: "POST" }),
    onSuccess: done,
  });
  const all = useMutation({
    mutationFn: () => api(`${base(labId)}/notifications/read-all/`, { method: "POST" }),
    onSuccess: done,
  });
  return { one, all };
}

export function useRetentionDue(labId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["labs", labId, "retention"],
    queryFn: () => api<RetentionItem[]>(`${base(labId!)}/retention/due/`),
    enabled: !!labId && enabled,
  });
}
