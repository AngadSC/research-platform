import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Sensor, SensorAlert, SensorDetail, SensorInput, SensorToken } from "@/lib/api-types";

const base = (labId: string) => `/api/labs/${labId}/sensors/`;
const LIVE = 60_000; // readings arrive every minute or so; the page keeps up on its own

/** Every sensor in the lab with its last 24 hours, or only the ones on `itemId`. */
export function useSensors(labId: string, itemId?: string, enabled = true) {
  return useQuery({
    queryKey: ["labs", labId, "sensors", itemId ?? "all"],
    queryFn: () => api<Sensor[]>(`${base(labId)}${itemId ? `?item=${itemId}` : ""}`),
    refetchInterval: LIVE,
    enabled,
  });
}

/** One sensor with its last 7 days and alert history. */
export function useSensor(labId: string, sensorId: string) {
  return useQuery({
    queryKey: ["labs", labId, "sensors", "one", sensorId],
    queryFn: () => api<SensorDetail>(`${base(labId)}${sensorId}/`),
    refetchInterval: LIVE,
  });
}

export function useSensorMutations(labId: string) {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ["labs", labId, "sensors"] });
  const post = <T>(url: string, body?: unknown) => api<T>(url, { method: "POST", body });
  return {
    create: useMutation({
      mutationFn: (v: SensorInput) => post<SensorDetail>(base(labId), v),
      onSuccess: done,
    }),
    update: useMutation({
      mutationFn: ({ id, ...v }: Partial<SensorInput> & { id: string }) =>
        api<SensorDetail>(`${base(labId)}${id}/`, { method: "PATCH", body: v }),
      onSuccess: done,
    }),
    remove: useMutation({
      mutationFn: (id: string) => api(`${base(labId)}${id}/`, { method: "DELETE" }),
      onSuccess: done,
    }),
    issueToken: useMutation({
      mutationFn: (id: string) => post<SensorToken>(`${base(labId)}${id}/token/`),
      onSuccess: done,
    }),
    revokeToken: useMutation({
      mutationFn: (id: string) => api(`${base(labId)}${id}/token/`, { method: "DELETE" }),
      onSuccess: done,
    }),
    testReading: useMutation({
      mutationFn: ({ id, value }: { id: string; value: number }) =>
        post<SensorDetail>(`${base(labId)}${id}/test-reading/`, { value }),
      onSuccess: done,
    }),
    acknowledge: useMutation({
      mutationFn: ({ id, note }: { id: string; note: string }) =>
        post<SensorAlert>(`${base(labId)}alerts/${id}/acknowledge/`, { note }),
      onSuccess: done,
    }),
  };
}
