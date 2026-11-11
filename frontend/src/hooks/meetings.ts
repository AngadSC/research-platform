import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  GoogleCalendarSync,
  GoogleCalendarSyncInput,
  GoogleEvent,
  SyncResult,
  VideoOptions,
} from "@/lib/api-types";

const base = (labId: string) => `/api/labs/${labId}/calendar`;

/** Which calls you can make on a new meeting, and which the site could offer once connected. */
export function useVideoOptions(labId: string) {
  return useQuery({
    queryKey: ["labs", labId, "video-options"],
    queryFn: () => api<VideoOptions>(`${base(labId)}/video-options/`),
  });
}

/** Your Google Calendar settings here (D255, D256): read, change, and sync now. */
export function useGoogleSync(labId: string) {
  const qc = useQueryClient();
  const key = ["labs", labId, "google-calendar"];
  const refresh = (data: GoogleCalendarSync) => {
    qc.setQueryData(key, data);
    void qc.invalidateQueries({ queryKey: ["labs", labId, "google-events"] });
  };
  return {
    status: useQuery({
      queryKey: key,
      queryFn: () => api<GoogleCalendarSync>(`${base(labId)}/google/`),
    }),
    change: useMutation({
      mutationFn: (v: GoogleCalendarSyncInput) =>
        api<GoogleCalendarSync>(`${base(labId)}/google/`, { method: "PATCH", body: v }),
      onSuccess: refresh,
    }),
    syncNow: useMutation({
      mutationFn: () => api<SyncResult>(`${base(labId)}/google/sync/`, { method: "POST" }),
      onSuccess: refresh,
    }),
  };
}

/** Your own Google events for the window, read live; [] until connected and switched on. */
export function useGoogleEvents(labId: string, from: string, to: string, enabled: boolean) {
  return useQuery({
    queryKey: ["labs", labId, "google-events", from, to],
    queryFn: () =>
      api<GoogleEvent[]>(
        `${base(labId)}/google/events/?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
      ),
    enabled,
    staleTime: 60_000,
  });
}

/** The local day a Google event belongs on, and the days it covers. */
export function googleOn(events: GoogleEvent[], iso: string): GoogleEvent[] {
  return events.filter((e) => {
    const first = e.starts_at ? localDay(e.starts_at) : e.date;
    const last = e.end_date ?? first;
    return first <= iso && iso <= last;
  });
}

const localDay = (stamp: string) => {
  const d = new Date(stamp);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
