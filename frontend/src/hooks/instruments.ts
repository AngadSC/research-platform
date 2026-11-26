import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, upload } from "@/lib/api";
import { useProjects } from "@/hooks/projects";
import type {
  DropLink,
  DropLinkCreated,
  InstrumentFile,
  InstrumentFileDetail,
  PublicDrop,
  SoftwareChoice,
} from "@/lib/api-types";

const base = (labId: string) => `/api/labs/${labId}`;

export const dropPath = (labId: string, itemId: string) =>
  `/labs/${labId}/instruments/${itemId}/drop`;

/** One short line on how reading a file went. */
export function parseLine(f: Pick<InstrumentFile, "status" | "title">): string {
  if (f.status === "pending") return "Reading the file…";
  if (f.status === "ok") return f.title ? `Read: ${f.title}` : "Read";
  if (f.status === "unsupported") return "No preview for this kind of file yet";
  return "Could not read this file";
}

/** Projects you can add files to, for the drop page and drop links. */
export function useContributableProjects(labId: string) {
  const { data, isLoading } = useProjects(labId);
  const projects = (data ?? []).filter(
    (p) => p.my_permissions.includes("edit_content") && p.status !== "archived",
  );
  return { projects, isLoading };
}

export function useSoftwareChoices() {
  return useQuery({
    queryKey: ["instrument-software"],
    queryFn: () => api<SoftwareChoice[]>("/api/instrument-software/"),
    staleTime: Infinity,
  });
}

/** Newest first, in projects you can see. Filter by instrument or project. */
export function useInstrumentFiles(
  labId: string,
  filter: { instrument?: string; project?: string },
  enabled = true,
) {
  const qs = new URLSearchParams(Object.entries(filter).filter(([, v]) => v) as [string, string][]);
  return useQuery({
    queryKey: ["labs", labId, "instrument-files", filter],
    queryFn: () => api<InstrumentFile[]>(`${base(labId)}/instrument-files/?${qs}`),
    enabled: enabled && !!labId,
    // keep asking while something is still being read
    refetchInterval: (q) => (q.state.data?.some((f) => f.status === "pending") ? 3000 : false),
  });
}

export function useInstrumentFile(labId: string, id: string | null) {
  return useQuery({
    queryKey: ["labs", labId, "instrument-files", "one", id],
    queryFn: () => api<InstrumentFileDetail>(`${base(labId)}/instrument-files/${id}/`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data?.status === "pending" ? 2000 : false),
  });
}

export function dropFile(
  labId: string,
  projectId: string,
  itemId: string,
  file: File,
  participant: boolean,
  onProgress?: (f: number) => void,
) {
  const form = new FormData();
  form.append("file", file);
  form.append("acknowledged_notice", "true");
  if (participant) form.append("contains_participant_data", "true");
  return upload<InstrumentFile>(
    `${base(labId)}/projects/${projectId}/instruments/${itemId}/files/`,
    form,
    onProgress,
  );
}

export function useDropLinks(labId: string, itemId: string) {
  const qc = useQueryClient();
  const key = ["labs", labId, "drop-links", itemId];
  const done = () => qc.invalidateQueries({ queryKey: key });
  return {
    list: useQuery({
      queryKey: key,
      queryFn: () => api<DropLink[]>(`${base(labId)}/instruments/${itemId}/drop-links/`),
    }),
    create: useMutation({
      mutationFn: (v: { project: string; label: string; expires_in_days: number | null }) =>
        api<DropLinkCreated>(`${base(labId)}/instruments/${itemId}/drop-links/`, {
          method: "POST",
          body: v,
        }),
      onSuccess: done,
    }),
    revoke: useMutation({
      mutationFn: (id: string) =>
        api(`${base(labId)}/instrument-drop-links/${id}/`, { method: "DELETE" }),
      onSuccess: done,
    }),
  };
}

/** The server's own sentence (an expired or turned-off link says so), else undefined. */
export const serverDetail = (e: unknown) =>
  e instanceof ApiError ? (e.body as { detail?: string } | null)?.detail : undefined;

/** The public page: no sign-in, the token is the only key. */
export function usePublicDrop(token: string) {
  return useQuery({
    queryKey: ["instrument-drop", token],
    queryFn: () => api<PublicDrop>(`/api/instrument-drop/?token=${encodeURIComponent(token)}`),
    retry: false,
  });
}

export function publicDropFile(
  token: string,
  file: File,
  participant: boolean,
  onProgress?: (f: number) => void,
) {
  const form = new FormData();
  form.append("token", token); // in the body, so it stays out of the address
  form.append("file", file);
  form.append("acknowledged_notice", "true");
  if (participant) form.append("contains_participant_data", "true");
  return upload<{ name: string; size_bytes: number }>("/api/instrument-drop/", form, onProgress);
}
