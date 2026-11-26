import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, upload } from "@/lib/api";
import type {
  Attachment,
  BoxDetail,
  BoxInput,
  SampleDetail,
  SampleImportResult,
  SampleInput,
  SampleNextCodes,
  Sample,
  StorageUnit,
  StorageUnitInput,
  Tube,
  TubeInput,
} from "@/lib/api-types";

const body = (v: unknown) => ({ body: v });
const base = (labId: string) => `/api/labs/${labId}`;
// One root for everything here: a tube change touches samples and the box map alike.
const root = (labId: string) => ["labs", labId, "samples"];

export interface SampleQuery {
  q?: string;
  kind?: string;
  status?: string;
  owner?: string;
}
export const sampleQs = (p: SampleQuery) => {
  const qs = new URLSearchParams(Object.entries(p).filter(([, v]) => v) as [string, string][]);
  return qs.size ? `?${qs}` : "";
};
export const sampleExportUrl = (labId: string, p: SampleQuery) =>
  `${base(labId)}/samples/export/${sampleQs(p)}`;
export const sampleFileUrl = (labId: string, sampleId: string, fileId: string) =>
  `${base(labId)}/samples/${sampleId}/files/${fileId}/`;

export function useSamples(labId: string, p: SampleQuery, enabled = true) {
  const qs = sampleQs(p);
  return useQuery({
    queryKey: [...root(labId), "list", qs],
    queryFn: () => api<Sample[]>(`${base(labId)}/samples/${qs}`),
    enabled,
  });
}

export const useNextCodes = (labId: string, enabled = true) =>
  useQuery({
    queryKey: [...root(labId), "next-codes"],
    queryFn: () => api<SampleNextCodes>(`${base(labId)}/samples/next-codes/`),
    enabled,
    staleTime: 0,
  });

export const useSample = (labId: string, sampleId: string) =>
  useQuery({
    queryKey: [...root(labId), "detail", sampleId],
    queryFn: () => api<SampleDetail>(`${base(labId)}/samples/${sampleId}/`),
  });

export function useSampleActions(labId: string) {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: root(labId) });
  const url = `${base(labId)}/samples/`;
  return {
    create: useMutation({
      mutationFn: (v: SampleInput) => api<SampleDetail>(url, { method: "POST", ...body(v) }),
      onSuccess: done,
    }),
    update: useMutation({
      mutationFn: ({ id, ...v }: Partial<SampleInput> & { id: string }) =>
        api<SampleDetail>(`${url}${id}/`, { method: "PATCH", ...body(v) }),
      onSuccess: done,
    }),
    remove: useMutation({
      mutationFn: (id: string) => api(`${url}${id}/`, { method: "DELETE" }),
      onSuccess: done,
    }),
    uploadFile: useMutation({
      mutationFn: (v: { id: string; file: File; onProgress?: (f: number) => void }) => {
        const form = new FormData();
        form.append("file", v.file);
        form.append("acknowledged_notice", "true");
        return upload(`${url}${v.id}/files/`, form, v.onProgress);
      },
      onSuccess: done,
    }),
    removeFile: useMutation({
      mutationFn: (v: { id: string; fileId: string }) =>
        api(`${url}${v.id}/files/${v.fileId}/`, { method: "DELETE" }),
      onSuccess: done,
    }),
  };
}

/** Preview a CSV of samples, or (commit=true) add every row. */
export function importSamples(labId: string, file: File, commit: boolean) {
  const form = new FormData();
  form.append("file", file);
  form.append("commit", String(commit));
  return upload<SampleImportResult>(`${base(labId)}/samples/import/`, form);
}

/** The files of one project, to pick one to link onto a sample. */
export const useProjectFiles = (labId: string, projectId: string) =>
  useQuery({
    queryKey: ["labs", labId, "projects", projectId, "attachments"],
    queryFn: () => api<Attachment[]>(`${base(labId)}/projects/${projectId}/attachments/`),
    enabled: !!projectId,
  });

export const useStorage = (labId: string, enabled = true) =>
  useQuery({
    queryKey: [...root(labId), "storage"],
    queryFn: () => api<StorageUnit[]>(`${base(labId)}/storage/`),
    enabled,
  });

export const useBox = (labId: string, boxId: string) =>
  useQuery({
    queryKey: [...root(labId), "box", boxId],
    queryFn: () => api<BoxDetail>(`${base(labId)}/storage/boxes/${boxId}/`),
    enabled: !!boxId,
  });

/** Freezers, boxes and tubes: add, change, remove. */
export function useStorageActions(labId: string) {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: root(labId) });
  const s = `${base(labId)}/storage/`;
  const useEdit = <I>(path: string) =>
    useMutation({
      mutationFn: ({ id, ...v }: Partial<I> & { id: string }) =>
        api(`${s}${path}${id}/`, { method: "PATCH", ...body(v) }),
      onSuccess: done,
    });
  const useDel = (path: string) =>
    useMutation({
      mutationFn: (id: string) => api(`${s}${path}${id}/`, { method: "DELETE" }),
      onSuccess: done,
    });
  return {
    addUnit: useMutation({
      mutationFn: (v: StorageUnitInput) => api<StorageUnit>(s, { method: "POST", ...body(v) }),
      onSuccess: done,
    }),
    editUnit: useEdit<StorageUnitInput>(""),
    removeUnit: useDel(""),
    addBox: useMutation({
      mutationFn: (v: BoxInput) => api<BoxDetail>(`${s}boxes/`, { method: "POST", ...body(v) }),
      onSuccess: done,
    }),
    editBox: useEdit<BoxInput>("boxes/"),
    removeBox: useDel("boxes/"),
    placeTube: useMutation({
      mutationFn: (v: TubeInput) => api<Tube>(`${s}tubes/`, { method: "POST", ...body(v) }),
      onSuccess: done,
    }),
    editTube: useEdit<TubeInput>("tubes/"),
    removeTube: useDel("tubes/"),
  };
}
