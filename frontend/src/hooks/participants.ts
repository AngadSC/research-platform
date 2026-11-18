import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  CellStatus,
  RegistryCell,
  RegistryCellInput,
  RegistryColumn,
  RegistryColumnInput,
  RegistryEvent,
  RegistryFile,
  RegistryParticipant,
  RegistryReason,
} from "@/lib/api-types";

const root = (labId: string, projectId: string) => `/api/labs/${labId}/projects/${projectId}`;
const keys = (labId: string, projectId: string) =>
  ["labs", labId, "projects", projectId, "registry"] as const;

export function useRegistry(labId: string, projectId: string) {
  const qc = useQueryClient();
  const k = keys(labId, projectId);
  const base = root(labId, projectId);
  const refresh = () => qc.invalidateQueries({ queryKey: k });

  const participants = useQuery({
    queryKey: [...k, "participants"],
    queryFn: () => api<RegistryParticipant[]>(`${base}/participants/`),
  });
  const columns = useQuery({
    queryKey: [...k, "columns"],
    queryFn: () => api<RegistryColumn[]>(`${base}/participant-components/`),
  });
  const cells = useQuery({
    queryKey: [...k, "cells"],
    queryFn: () => api<RegistryCell[]>(`${base}/participant-cells/`),
  });

  const addParticipants = useMutation({
    mutationFn: (v: { codes: string[]; group?: string; cohort?: string }) =>
      api<RegistryParticipant[]>(`${base}/participants/`, { method: "POST", body: v }),
    onSuccess: refresh,
  });
  const addColumn = useMutation({
    mutationFn: (v: RegistryColumnInput) =>
      api<RegistryColumn>(`${base}/participant-components/`, { method: "POST", body: v }),
    onSuccess: refresh,
  });
  const removeColumn = useMutation({
    mutationFn: (id: string) =>
      api<{ cells_removed: number }>(`${base}/participant-components/${id}/`, {
        method: "DELETE",
      }),
    onSuccess: refresh,
  });
  const archive = useMutation({
    mutationFn: (v: { id: string; archived: boolean }) =>
      api<RegistryParticipant>(
        `${base}/participants/${v.id}/${v.archived ? "archive" : "restore"}/`,
        { method: "POST" },
      ),
    onSuccess: refresh,
  });

  /** Optimistic: the grid shows the new value at once and rolls back when the server refuses. */
  const setCell = useMutation({
    mutationFn: (v: { participant: string; component: string; patch: RegistryCellInput }) =>
      api<RegistryCell>(`${base}/participants/${v.participant}/cells/${v.component}/`, {
        method: "PATCH",
        body: v.patch,
      }),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: [...k, "cells"] });
      const prev = qc.getQueryData<RegistryCell[]>([...k, "cells"]);
      if (prev) {
        const status = v.patch.status as CellStatus | undefined;
        const next = prev.some(
          (c) => c.participant === v.participant && c.component === v.component,
        )
          ? prev.map((c) =>
              c.participant === v.participant && c.component === v.component
                ? { ...c, ...(v.patch as Partial<RegistryCell>), ...(status ? { status } : {}) }
                : c,
            )
          : [
              ...prev,
              {
                id: `pending-${v.participant}-${v.component}`,
                participant: v.participant,
                component: v.component,
                status: status ?? "not_started",
                reason: null,
                owner: null,
                due_date: null,
                collected_on: null,
                note: "",
                files: [],
                suggested_status: null,
                updated_at: new Date().toISOString(),
                ...(v.patch as Partial<RegistryCell>),
              } as RegistryCell,
            ];
        qc.setQueryData([...k, "cells"], next);
      }
      return { prev };
    },
    onError: (_e, _v, ctx) => ctx?.prev && qc.setQueryData([...k, "cells"], ctx.prev),
    onSettled: refresh,
  });

  const addFile = useMutation({
    mutationFn: (v: { cell: string; url: string; title?: string; role?: RegistryFile["role"] }) =>
      api<RegistryFile>(`${base}/participant-cells/${v.cell}/files/`, {
        method: "POST",
        body: { url: v.url, title: v.title, role: v.role },
      }),
    onSuccess: refresh,
  });
  const removeFile = useMutation({
    mutationFn: (id: string) => api(`${base}/participant-files/${id}/`, { method: "DELETE" }),
    onSuccess: refresh,
  });

  const createTasks = useMutation({
    mutationFn: (v: {
      cells: { participant: string; component: string }[];
      mode: "cell" | "participant" | "component";
      assignee?: string | null;
      due_date?: string | null;
    }) =>
      api<{ created: number; skipped: number; tasks: string[] }>(`${base}/participant-tasks/`, {
        method: "POST",
        body: v,
      }),
    onSuccess: () => {
      void refresh();
      void qc.invalidateQueries({ queryKey: ["labs", labId, "projects", projectId, "tasks"] });
    },
  });

  return {
    createTasks,
    participants,
    columns,
    cells,
    addParticipants,
    addColumn,
    removeColumn,
    archive,
    setCell,
    addFile,
    removeFile,
  };
}

/** Archived participants (never deleted, D308), for the registry's "archived" view. */
export function useArchivedParticipants(labId: string, projectId: string) {
  return useQuery({
    queryKey: [...keys(labId, projectId), "archived"],
    queryFn: () => api<RegistryParticipant[]>(`${root(labId, projectId)}/participants/?archived=1`),
  });
}

export function useReasons(labId: string) {
  return useQuery({
    queryKey: ["labs", labId, "participant-reasons"],
    queryFn: () => api<RegistryReason[]>(`/api/labs/${labId}/participant-reasons/`),
  });
}

export function useParticipantEvents(labId: string, projectId: string, participantId: string) {
  return useQuery({
    queryKey: [...keys(labId, projectId), "events", participantId],
    queryFn: () =>
      api<RegistryEvent[]>(`${root(labId, projectId)}/participants/${participantId}/events/`),
  });
}

// ---------------------------------------------------------------- import, matching, link health

export interface ImportPreview {
  headers: string[];
  rows: string[][];
  total: number;
  blocked_headers: string[];
  link_columns: string[];
}
export interface ImportMapping {
  code: string;
  group?: string;
  cohort?: string;
  enrolment_status?: string;
  components: { column: string; name?: string; category?: string }[];
}
export interface ImportResult {
  created: number;
  updated: number;
  skipped: number;
  links: number;
  components_created: number;
  attention: { row: number; message: string }[];
  attention_total: number;
  dry_run: boolean;
  run?: string;
}
export interface ImportRun {
  id: string;
  source: string;
  summary: Partial<ImportResult>;
  undone_at: string | null;
  created_at: string;
  can_undo: boolean;
}
export interface FileMatch {
  name: string;
  url: string;
  participant: string | null;
  participant_code?: string;
  component: string | null;
  component_name?: string;
  confidence: "high" | "medium" | "low" | "none";
}
export interface LinkHealth {
  counts: {
    total: number;
    ok: number;
    unchecked: number;
    problems: number;
    changed_since_verified: number;
  };
  problems: {
    file: string;
    cell: string;
    participant: string;
    component: string;
    title: string;
    url: string;
    state: string;
  }[];
  changed: { cell: string; participant: string; component: string }[];
}

export function useImports(labId: string, projectId: string, enabled = true) {
  const qc = useQueryClient();
  const base = root(labId, projectId);
  const k = keys(labId, projectId);
  const refresh = () => qc.invalidateQueries({ queryKey: k });
  const history = useQuery({
    queryKey: [...k, "imports"],
    queryFn: () => api<ImportRun[]>(`${base}/participant-imports/`),
    enabled,
  });
  const preview = useMutation({
    mutationFn: (csv: string) =>
      api<ImportPreview>(`${base}/participant-imports/preview/`, {
        method: "POST",
        body: { csv },
      }),
  });
  const run = useMutation({
    mutationFn: (v: { csv: string; mapping: ImportMapping; dry_run: boolean }) =>
      api<ImportResult>(`${base}/participant-imports/`, { method: "POST", body: v }),
    onSuccess: (r) => !r.dry_run && refresh(),
  });
  const undo = useMutation({
    mutationFn: (id: string) =>
      api<ImportRun>(`${base}/participant-imports/${id}/undo/`, { method: "POST" }),
    onSuccess: refresh,
  });
  const match = useMutation({
    mutationFn: (v: { files: { name: string; url: string }[]; pattern: string }) =>
      api<{ matches: FileMatch[] }>(`${base}/participant-file-matches/`, {
        method: "POST",
        body: v,
      }),
  });
  const attach = useMutation({
    mutationFn: (items: { participant: string; component: string; url: string }[]) =>
      api<{ attached: number; skipped: number }>(`${base}/participant-file-matches/attach/`, {
        method: "POST",
        body: { items },
      }),
    onSuccess: refresh,
  });
  return { history, preview, run, undo, match, attach };
}

export function useLinkHealth(labId: string, projectId: string) {
  const qc = useQueryClient();
  const base = root(labId, projectId);
  const k = keys(labId, projectId);
  const health = useQuery({
    queryKey: [...k, "health"],
    queryFn: () => api<LinkHealth>(`${base}/participant-link-health/`),
  });
  const check = useMutation({
    mutationFn: () =>
      api<{ checked: number; problems: number }>(`${base}/participant-link-health/refresh/`, {
        method: "POST",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: k }),
  });
  return { health, check };
}

export interface OverviewItem {
  project: string;
  project_name: string;
  participant: string;
  participant_id: string;
  component: string;
  status: CellStatus;
  due_date: string | null;
  at: string;
}
export interface LabOverview {
  projects: {
    id: string;
    name: string;
    color: string;
    participants: number;
    percent: number;
    missing: number;
    overdue: number;
    needs_review: number;
  }[];
  by_component: { name: string; percent: number; cells: number }[];
  missing_by_reason: { reason: string; count: number }[];
  translation_pending: { group: string; count: number }[];
  waiting_on_me: OverviewItem[];
  recent: OverviewItem[];
}

export function useLabOverview(labId: string, enabled = true) {
  return useQuery({
    queryKey: ["labs", labId, "participant-overview"],
    queryFn: () => api<LabOverview>(`/api/labs/${labId}/participant-overview/`),
    enabled: enabled && !!labId,
  });
}

// ---------------------------------------------------------------- rules, locked sets, flow

export interface RuleSpec {
  requires: string[];
  groups: string[];
  exclude_enrolment: string[];
}
export interface Rule {
  id: string;
  name: string;
  description: string;
  version: number;
  spec: RuleSpec;
}
export interface RuleResult {
  eligible: string[];
  one_away: { code: string; blocking: { column: string; status: string }[] }[];
  not_eligible: number;
  not_eligible_why: Record<string, number>;
}
export interface LockedSet {
  id: string;
  name: string;
  rule: string | null;
  rule_version: number;
  size: number;
  locked_at: string;
  analysis: string | null;
  supersedes: string | null;
}
export interface SetDetail {
  set: LockedSet;
  codes: string[];
  changes: { participant: string; column: string; kind: string }[];
}
interface Counted {
  count: number;
  small: boolean;
}
export interface Flow {
  screened: Counted;
  enrolled: Counted;
  completed: Counted;
  withdrawn: Counted;
  ineligible: Counted;
  excluded: (Counted & { reason: string })[];
  analysed: Counted | null;
  groups: (Counted & { group: string })[];
  set: string | null;
  small_cell_limit: number;
  warning: string | null;
}

export function useRules(labId: string, projectId: string, enabled = true) {
  const qc = useQueryClient();
  const base = root(labId, projectId);
  const k = [...keys(labId, projectId), "rules"];
  const refresh = () => qc.invalidateQueries({ queryKey: k });
  const rules = useQuery({
    queryKey: [...k, "list"],
    queryFn: () => api<Rule[]>(`${base}/participant-rules/`),
    enabled,
  });
  const save = useMutation({
    mutationFn: (v: { id?: string; name: string; description?: string; spec: RuleSpec }) =>
      v.id
        ? api<Rule>(`${base}/participant-rules/${v.id}/`, { method: "PATCH", body: v })
        : api<Rule>(`${base}/participant-rules/`, { method: "POST", body: v }),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`${base}/participant-rules/${id}/`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  const preview = useMutation({
    mutationFn: (spec: Partial<RuleSpec>) =>
      api<RuleResult>(`${base}/participant-rules/preview/`, { method: "POST", body: spec }),
  });
  const sets = useQuery({
    queryKey: [...k, "sets"],
    queryFn: () => api<LockedSet[]>(`${base}/analysis-sets/`),
    enabled,
  });
  const lock = useMutation({
    mutationFn: (v: { name: string; rule: string }) =>
      api<LockedSet>(`${base}/analysis-sets/`, { method: "POST", body: v }),
    onSuccess: refresh,
  });
  const newVersion = useMutation({
    mutationFn: (id: string) =>
      api<LockedSet>(`${base}/analysis-sets/${id}/new-version/`, { method: "POST" }),
    onSuccess: refresh,
  });
  return { rules, save, remove, preview, sets, lock, newVersion };
}

export function useSetDetail(labId: string, projectId: string, id?: string) {
  return useQuery({
    queryKey: [...keys(labId, projectId), "rules", "set", id],
    queryFn: () => api<SetDetail>(`${root(labId, projectId)}/analysis-sets/${id}/`),
    enabled: !!id,
  });
}

export function useFlow(labId: string, projectId: string, setId?: string) {
  return useQuery({
    queryKey: [...keys(labId, projectId), "flow", setId ?? "none"],
    queryFn: () =>
      api<Flow>(`${root(labId, projectId)}/participant-flow/${setId ? `?set=${setId}` : ""}`),
  });
}

export const logFlowExport = (labId: string, projectId: string, kind: "table" | "svg" | "png") =>
  api(`${root(labId, projectId)}/participant-flow/export/`, { method: "POST", body: { kind } });
