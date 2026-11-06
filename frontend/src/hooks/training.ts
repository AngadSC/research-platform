import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, upload } from "@/lib/api";
import type {
  Attachment,
  TrainingCompliance,
  TrainingExpiring,
  TrainingRecord,
  TrainingRecordInput,
  TrainingRequirement,
  TrainingRequirementInput,
} from "@/lib/api-types";

const base = (labId: string) => `/api/labs/${labId}/training`;
const root = (labId: string) => ["labs", labId, "training"] as const;
const body = (v: unknown) => ({ body: v });

export const useTrainingRequirements = (labId: string) =>
  useQuery({
    queryKey: [...root(labId), "requirements"],
    queryFn: () => api<TrainingRequirement[]>(`${base(labId)}/requirements/`),
  });

/** Everyone in the lab, for pi and lab_admin only (the server answers 403 to the rest). */
export const useCompliance = (labId: string, enabled = true) =>
  useQuery({
    queryKey: [...root(labId), "compliance"],
    queryFn: () => api<TrainingCompliance>(`${base(labId)}/compliance/`),
    enabled,
  });

export const useMyTraining = (labId: string) =>
  useQuery({
    queryKey: [...root(labId), "my"],
    queryFn: () => api<TrainingCompliance>(`${base(labId)}/my/`),
  });

/** The requester's own records, or everyone's for a manager. */
export const useTrainingRecords = (labId: string) =>
  useQuery({
    queryKey: [...root(labId), "records"],
    queryFn: () => api<TrainingRecord[]>(`${base(labId)}/records/`),
  });

export const useExpiringTraining = (labId: string, days = 60, enabled = true) =>
  useQuery({
    queryKey: [...root(labId), "expiring", days],
    queryFn: () => api<TrainingExpiring>(`${base(labId)}/expiring/?days=${days}`),
    enabled,
  });

export function useTrainingMutations(labId: string) {
  const qc = useQueryClient();
  // records, compliance and the onboarding checklist all depend on each other
  const done = () => {
    void qc.invalidateQueries({ queryKey: root(labId) });
    void qc.invalidateQueries({ queryKey: ["labs", labId, "onboarding"] });
  };
  return {
    createRequirement: useMutation({
      mutationFn: (v: TrainingRequirementInput) =>
        api<TrainingRequirement>(`${base(labId)}/requirements/`, { method: "POST", ...body(v) }),
      onSuccess: done,
    }),
    removeRequirement: useMutation({
      mutationFn: (id: string) => api(`${base(labId)}/requirements/${id}/`, { method: "DELETE" }),
      onSuccess: done,
    }),
    createRecord: useMutation({
      mutationFn: (v: TrainingRecordInput) =>
        api<TrainingRecord>(`${base(labId)}/records/`, { method: "POST", ...body(v) }),
      onSuccess: done,
    }),
    removeRecord: useMutation({
      mutationFn: (id: string) => api(`${base(labId)}/records/${id}/`, { method: "DELETE" }),
      onSuccess: done,
    }),
    verify: useMutation({
      mutationFn: (id: string) =>
        api<TrainingRecord>(`${base(labId)}/records/${id}/verify/`, { method: "POST" }),
      onSuccess: done,
    }),
    uploadCertificate: useMutation({
      mutationFn: (v: { id: string; file: File }) => {
        const form = new FormData();
        form.append("file", v.file);
        form.append("acknowledged_notice", "true");
        return upload<Attachment>(`${base(labId)}/records/${v.id}/certificate/`, form);
      },
      onSuccess: done,
    }),
  };
}

export const certificateUrl = (labId: string, recordId: string) =>
  `${base(labId)}/records/${recordId}/certificate/`;
