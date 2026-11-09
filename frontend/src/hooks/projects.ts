import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMe } from "@/hooks/workspace";
import { api, upload } from "@/lib/api";
import type {
  Attachment,
  Deadline,
  DeadlineInput,
  Project,
  ProjectInput,
  ProjectMembership,
  ProjectRole,
  Task,
  TaskInput,
  TaskPost,
  TaskView,
  TaskStatus,
  User,
} from "@/lib/api-types";

const body = (b: unknown) => ({ body: b });
const base = (labId: string) => `/api/labs/${labId}`;
const pKey = (labId: string, projectId: string) => ["labs", labId, "projects", projectId] as const;

export function useProjects(labId: string | undefined) {
  return useQuery({
    queryKey: ["labs", labId, "projects"],
    queryFn: () => api<Project[]>(`${base(labId!)}/projects/`),
    enabled: !!labId,
  });
}
export function useProject(labId: string | undefined, projectId: string | undefined) {
  return useQuery({
    queryKey: pKey(labId ?? "", projectId ?? ""),
    queryFn: () => api<Project>(`${base(labId!)}/projects/${projectId}/`),
    enabled: !!labId && !!projectId,
  });
}
export function useCreateProject(labId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: ProjectInput) =>
      api<Project>(`${base(labId)}/projects/`, { method: "POST", ...body(v) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labs", labId, "projects"] }),
  });
}
export function useUpdateProject(labId: string, projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: Partial<ProjectInput>) =>
      api<Project>(`${base(labId)}/projects/${projectId}/`, { method: "PATCH", ...body(v) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labs", labId, "projects"] }),
  });
}
export function useDeleteProject(labId: string, projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api(`${base(labId)}/projects/${projectId}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["labs", labId, "projects"] }),
  });
}

// Generic list + create/update/delete for a project sub-collection.
function useSub<T, I>(
  labId: string,
  projectId: string,
  name: "deadlines" | "members" | "tasks",
  flat: "deadlines" | "project-members" | "tasks",
) {
  const qc = useQueryClient();
  const key = [...pKey(labId, projectId), name];
  const refresh = () => qc.invalidateQueries({ queryKey: key });
  const list = useQuery({
    queryKey: key,
    queryFn: () => api<T[]>(`${base(labId)}/projects/${projectId}/${name}/`),
  });
  const create = useMutation({
    mutationFn: (v: I) =>
      api<T>(`${base(labId)}/projects/${projectId}/${name}/`, { method: "POST", ...body(v) }),
    onSuccess: refresh,
  });
  const update = useMutation({
    mutationFn: (v: { id: string; patch: Partial<I> | { role: ProjectRole } }) =>
      api<T>(`${base(labId)}/${flat}/${v.id}/`, { method: "PATCH", ...body(v.patch) }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`${base(labId)}/${flat}/${id}/`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  return { list, create, update, remove, key };
}

export const useDeadlines = (l: string, p: string) =>
  useSub<Deadline, DeadlineInput>(l, p, "deadlines", "deadlines");
export const useProjectMembers = (l: string, p: string) =>
  useSub<ProjectMembership, { user: string; role: ProjectRole }>(
    l,
    p,
    "members",
    "project-members",
  );

/** Column order is the order of `position` within each status. */
export function moveTask(tasks: Task[], id: string, status: TaskStatus, index: number): Task[] {
  const moved = tasks.find((t) => t.id === id);
  if (!moved) return tasks;
  const byPos = (a: Task, b: Task) => a.position - b.position;
  const target = tasks.filter((t) => t.status === status && t.id !== id).sort(byPos);
  target.splice(Math.min(index, target.length), 0, { ...moved, status });
  const out = new Map<string, Task>();
  target.forEach((t, i) => out.set(t.id, { ...t, position: i }));
  if (moved.status !== status)
    tasks
      .filter((t) => t.status === moved.status && t.id !== id)
      .sort(byPos)
      .forEach((t, i) => out.set(t.id, { ...t, position: i }));
  return tasks.map((t) => out.get(t.id) ?? t);
}

export function useTasks(labId: string, projectId: string) {
  const qc = useQueryClient();
  const { list, create, update, key } = useSub<Task, TaskInput>(labId, projectId, "tasks", "tasks");
  // Optimistic delete with rollback.
  const remove = useMutation({
    mutationFn: (id: string) => api(`${base(labId)}/tasks/${id}/`, { method: "DELETE" }),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<Task[]>(key);
      if (prev)
        qc.setQueryData(
          key,
          prev.filter((t) => t.id !== id),
        );
      return { prev };
    },
    onError: (_e, _v, ctx) => ctx?.prev && qc.setQueryData(key, ctx.prev),
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
  // Optimistic move; the previous list is restored if the server refuses.
  const move = useMutation({
    mutationFn: (v: { id: string; status: TaskStatus; position: number }) =>
      api<Task>(`${base(labId)}/tasks/${v.id}/`, {
        method: "PATCH",
        ...body({ status: v.status, position: v.position }),
      }),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<Task[]>(key);
      if (prev) qc.setQueryData(key, moveTask(prev, v.id, v.status, v.position));
      return { prev };
    },
    onError: (_e, _v, ctx) => ctx?.prev && qc.setQueryData(key, ctx.prev),
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
  return { list, create, update, remove, move };
}

export function useAttachments(labId: string, projectId: string) {
  const qc = useQueryClient();
  const key = [...pKey(labId, projectId), "attachments"];
  const list = useQuery({
    queryKey: key,
    queryFn: () => api<Attachment[]>(`${base(labId)}/projects/${projectId}/attachments/`),
  });
  // The notice is acknowledged by the caller on every upload; nothing is remembered here.
  const uploadFile = useMutation({
    mutationFn: (v: { file: File; onProgress?: (f: number) => void; folder?: string | null }) => {
      const form = new FormData();
      form.append("file", v.file);
      form.append("acknowledged_notice", "true");
      if (v.folder) form.append("folder", v.folder);
      return upload<Attachment>(
        `${base(labId)}/projects/${projectId}/attachments/`,
        form,
        v.onProgress,
      );
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`${base(labId)}/attachments/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });
  return { list, uploadFile, remove };
}

/** The only way files are fetched: the authenticated same-origin endpoint. */
export const downloadUrl = (labId: string, attachmentId: string) =>
  `${base(labId)}/attachments/${attachmentId}/download/`;

export function useAttachment(labId: string, attachmentId: string) {
  return useQuery({
    queryKey: ["labs", labId, "attachments", attachmentId],
    queryFn: () => api<Attachment>(`${base(labId)}/attachments/${attachmentId}/`),
    enabled: !!attachmentId,
  });
}

// ---------------------------------------------------------------- task thread and links (Run 4)

/** Board unless the account says list (D143). `ready` is false until /api/me/ has answered. */
export function useTaskView() {
  const qc = useQueryClient();
  const me = useMe();
  const prefs = (me.data as { preferences?: { task_view?: TaskView } } | undefined)?.preferences;
  const saved = prefs?.task_view;
  const save = useMutation({
    mutationFn: (task_view: TaskView) =>
      api<User>("/api/me/", { method: "PATCH", ...body({ preferences: { task_view } }) }),
    onSuccess: (u) => qc.setQueryData(["me"], u),
  });
  return {
    ready: !me.isPending,
    saved: saved === "list" ? ("list" as const) : ("board" as const),
    save: save.mutate,
  };
}

const postsKey = (labId: string, taskId: string) => ["labs", labId, "tasks", taskId, "posts"];

/** Polls so a teammate's update appears without a reload. */
export function useTaskPosts(labId: string, taskId: string) {
  const qc = useQueryClient();
  const key = postsKey(labId, taskId);
  const list = useQuery({
    queryKey: key,
    queryFn: () => api<TaskPost[]>(`${base(labId)}/tasks/${taskId}/posts/`),
    refetchInterval: 10_000,
  });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: key });
    void qc.invalidateQueries({ queryKey: ["labs", labId, "projects"] }); // post_count
  };
  const create = useMutation({
    mutationFn: (text: string) =>
      api<TaskPost>(`${base(labId)}/tasks/${taskId}/posts/`, {
        method: "POST",
        ...body({ body: text }),
      }),
    onSuccess: refresh,
  });
  const edit = useMutation({
    mutationFn: (v: { id: string; body: string }) =>
      api<TaskPost>(`${base(labId)}/task-posts/${v.id}/`, {
        method: "PATCH",
        ...body({ body: v.body }),
      }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`${base(labId)}/task-posts/${id}/`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  return { list, create, edit, remove };
}

export type TaskLinkKind = "documents" | "attachments";

export function useTaskLinks(labId: string, projectId: string, taskId: string) {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: [...pKey(labId, projectId), "tasks"] });
  const attach = useMutation({
    mutationFn: (v: { kind: TaskLinkKind; id: string }) =>
      api<Task>(`${base(labId)}/tasks/${taskId}/${v.kind}/`, {
        method: "POST",
        ...body({ id: v.id }),
      }),
    onSuccess: done,
  });
  const detach = useMutation({
    mutationFn: (v: { kind: TaskLinkKind; id: string }) =>
      api<Task>(`${base(labId)}/tasks/${taskId}/${v.kind}/${v.id}/`, { method: "DELETE" }),
    onSuccess: done,
  });
  return { attach, detach };
}
