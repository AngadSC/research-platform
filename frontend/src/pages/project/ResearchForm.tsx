import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Upload } from "lucide-react";
import { useRef, useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { FormError } from "@/components/shared/FormError";
import { FormField } from "@/components/shared/FormField";
import { ParticipantCheckbox } from "@/components/shared/ParticipantData";
import { ReferencesEditor } from "@/components/shared/References";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { root, useSaveRecord } from "@/hooks/research";
import { useAttachments } from "@/hooks/projects";
import { api } from "@/lib/api";
import { personName, type Dataset, type Decision, type Reference } from "@/lib/api-types";
import { formErrors } from "@/lib/forms";
import {
  isCommit,
  isHttpUrl,
  MANUSCRIPT_STATUSES,
  type AnyRecord,
  type Kind,
} from "@/lib/research";
import { cleanReferences, validateReferences, type RefErrors } from "@/lib/references";
import { UploadDialog } from "@/pages/project/UploadDialog";
import { FromDriveButton } from "@/components/shared/FromDriveButton";
import { attachFromDrive } from "@/lib/drive";

type Source = Kind | "documents" | "attachments" | "members";
type Type = "text" | "textarea" | "url" | "date" | "select" | "multi" | "status";
interface Field {
  name: string;
  label: string;
  type: Type;
  required?: boolean;
  hint?: string;
  source?: Source;
}

const F = (name: string, label: string, type: Type, extra: Partial<Field> = {}): Field => ({
  name,
  label,
  type,
  ...extra,
});

const FIELDS: Record<Kind, Field[]> = {
  datasets: [
    F("name", "Name", "text", { required: true }),
    F("version_label", "Version", "text", { required: true, hint: "For example v1 or 2026-03." }),
    F("previous_version", "New version of", "select", {
      source: "datasets",
      hint: "Optional. Pick the dataset this one replaces.",
    }),
    F("location_text", "Where it lives", "text", { hint: "For example a secure server path." }),
    F("location_url", "Link to the data", "url"),
    F("controlled_by", "Who controls access", "select", { source: "members" }),
    F("access_notes", "How to get access", "textarea"),
    F("checksum", "Checksum", "text", { hint: "Optional, to show the data has not changed." }),
  ],
  analyses: [
    F("title", "Title", "text", { required: true }),
    F("description", "Description", "textarea"),
    F("code_repo_url", "Code repository link", "url", {
      hint: "Use this with a commit, or attach the code below.",
    }),
    F("code_commit", "Commit", "text", { hint: "7 to 40 characters, 0-9 and a-f." }),
    F("code_attachment", "Or attach the code", "select", { source: "attachments" }),
    F("datasets", "Datasets used", "multi", { source: "datasets" }),
  ],
  results: [
    F("title", "Title", "text", { required: true }),
    F("summary", "Summary", "textarea"),
    F("analysis", "Analysis that produced it", "select", { source: "analyses", required: true }),
    F("attachments", "Figures and tables", "multi", { source: "attachments" }),
  ],
  decisions: [
    F("title", "Title", "text", { required: true }),
    F("rationale", "Why", "textarea"),
    F("decided_on", "Decided on", "date"),
    F("supporting_documents", "Supporting documents", "multi", { source: "documents" }),
    F("supporting_attachments", "Supporting files", "multi", { source: "attachments" }),
    F("datasets", "Datasets", "multi", { source: "datasets" }),
    F("analyses", "Analyses", "multi", { source: "analyses" }),
    F("results", "Results", "multi", { source: "results" }),
  ],
  manuscripts: [
    F("title", "Title", "text", { required: true }),
    F("url", "Link to the manuscript", "url", {
      required: true,
      hint: "Overleaf or Google Docs.",
    }),
    F("status", "Status", "status"),
    F("results", "Results used", "multi", { source: "results" }),
  ],
};

type Values = Record<string, string | string[]>;

/** Server limits by field name. Every kind uses the same limit for a shared name. */
const RESEARCH_MAX_LENGTH: Record<string, number> = {
  name: 200,
  version_label: 100,
  checksum: 140,
  title: 300,
  code_commit: 40,
  code_repo_url: 200,
  location_url: 200,
  url: 200,
};

/** Client-side checks; messages say what to do. Exported for tests. */
// eslint-disable-next-line react-refresh/only-export-components -- pure helper, also unit-tested
export function validate(kind: Kind, v: Values): Record<string, string> {
  const e: Record<string, string> = {};
  const s = (n: string) => ((v[n] as string | undefined) ?? "").trim();
  for (const f of FIELDS[kind]) {
    if (f.required && !s(f.name)) e[f.name] = `Enter ${f.label.toLowerCase()}`;
    else if (f.type === "url" && s(f.name) && !isHttpUrl(s(f.name)))
      e[f.name] = "Enter a link starting with http:// or https://";
  }
  if (kind === "analyses") {
    if (s("code_commit") && !isCommit(s("code_commit")))
      e.code_commit = "Enter 7 to 40 characters, using only 0-9 and a-f";
    if (!e.code_repo_url && !s("code_attachment") && !(s("code_repo_url") && s("code_commit")))
      e.code_repo_url = "Add a repository link and commit, or attach the code";
  }
  return e;
}

const NULLABLE = new Set(["previous_version", "controlled_by", "code_attachment"]);
const initial = (kind: Kind, rec?: AnyRecord): Values =>
  Object.fromEntries(
    FIELDS[kind].map((f) => {
      const x = (rec as unknown as Record<string, unknown> | undefined)?.[f.name];
      if (f.type === "multi")
        return [f.name, Array.isArray(x) ? x.map((r: { id: string }) => r.id) : []];
      if (x && typeof x === "object") return [f.name, (x as { id: string }).id];
      return [f.name, (x as string | undefined) ?? (f.type === "status" ? "drafting" : "")];
    }),
  );

interface Row {
  id: string;
  name?: string;
  title?: string;
  version_label?: string;
  original_filename?: string;
  user?: { id: string; display_name?: string; email: string };
}
function useOptions(labId: string, projectId: string, source: Source) {
  return useQuery({
    queryKey: [...root(labId), "opts", projectId, source],
    queryFn: async () => {
      const rows = await api<Row[]>(`/api/labs/${labId}/projects/${projectId}/${source}/`);
      return rows.map((r) => ({
        id: r.user?.id ?? r.id,
        label: r.user
          ? personName(r.user)
          : (r.original_filename ?? (r.name ? `${r.name} (${r.version_label})` : r.title)) || r.id,
      }));
    },
  });
}

const selectCls =
  "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none";

interface Props {
  labId: string;
  projectId: string;
  kind: Kind;
  record?: AnyRecord;
  /** A new dataset version starts from this one: same details, "New version of" set to it. */
  prefill?: Dataset;
  onSaved: (r: { id: string }) => void;
  onCancel: () => void;
}

export function ResearchForm({
  labId,
  projectId,
  kind,
  record,
  prefill,
  onSaved,
  onCancel,
}: Props) {
  const [v, setV] = useState<Values>(() =>
    prefill
      ? { ...initial(kind, prefill), version_label: "", checksum: "", previous_version: prefill.id }
      : initial(kind, record),
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string>();
  const [refs, setRefs] = useState<Reference[]>(() =>
    kind === "decisions" ? ((record as Decision | undefined)?.references ?? []) : [],
  );
  const [refErrors, setRefErrors] = useState<RefErrors[]>([]);
  const [participant, setParticipant] = useState(
    kind === "datasets" &&
      !!((record ?? prefill) as Dataset | undefined)?.contains_participant_data,
  );
  const [uploading, setUploading] = useState(false);
  const save = useSaveRecord<{ id: string }>(labId, projectId, kind, record?.id);
  const { uploadFile } = useAttachments(labId, projectId);
  const qc = useQueryClient();
  const set = (n: string, x: string | string[]) => setV((p) => ({ ...p, [n]: x }));

  function submit(ev: FormEvent) {
    ev.preventDefault();
    const errs = validate(kind, v);
    const rerrs = kind === "decisions" ? validateReferences(refs) : [];
    setErrors(errs);
    setRefErrors(rerrs);
    setFormError(undefined);
    if (Object.keys(errs).length || rerrs.some((e) => Object.keys(e).length)) return;
    const body: Record<string, unknown> = {};
    for (const f of FIELDS[kind]) {
      const x = v[f.name];
      if (f.type === "date" && !x) continue;
      body[f.name] = NULLABLE.has(f.name) && !x ? null : typeof x === "string" ? x.trim() : x;
    }
    if (kind === "decisions") body.references = cleanReferences(refs);
    if (kind === "datasets") body.contains_participant_data = participant;
    save.mutate(body, {
      onSuccess: (r) => {
        toast.success("Saved");
        onSaved(r);
      },
      onError: (e) => {
        const { fields, form } = formErrors(
          e,
          FIELDS[kind].map((f) => f.name),
        );
        setErrors(fields);
        setFormError(form);
      },
    });
  }

  return (
    <form onSubmit={submit} noValidate className="grid gap-4">
      {kind === "datasets" && (
        <p
          role="note"
          className="rounded-md border border-primary/40 bg-primary/10 p-3 text-sm font-medium"
        >
          Store a pointer only. Do not upload participant data.
        </p>
      )}
      {kind === "analyses" && (
        <p role="note" className="text-sm text-muted-foreground">
          <span className="text-destructive">*</span> Required. Code is also required: add a
          repository link and commit, or attach the code.
        </p>
      )}
      <FormError message={formError} />
      {FIELDS[kind].map((f) => (
        <FormField
          key={f.name}
          label={f.label}
          hint={f.hint}
          required={f.required}
          error={errors[f.name]}
        >
          {(p) =>
            f.type === "textarea" ? (
              <Textarea
                {...p}
                maxLength={RESEARCH_MAX_LENGTH[f.name]}
                value={v[f.name] as string}
                onChange={(e) => set(f.name, e.target.value)}
              />
            ) : f.type === "multi" ? (
              <Multi
                {...{ labId, projectId, f }}
                id={p.id}
                selected={v[f.name] as string[]}
                onChange={(x) => set(f.name, x)}
                extra={
                  kind === "results" && (
                    <span className="flex flex-wrap gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => setUploading(true)}
                      >
                        <Upload aria-hidden /> Upload a figure
                      </Button>
                      <FromDriveButton
                        labId={labId}
                        onPick={async (file) => {
                          const a = await attachFromDrive(
                            `/api/labs/${labId}/projects/${projectId}/attachments/`,
                            file.id,
                          );
                          setV((p) => ({
                            ...p,
                            attachments: [...(p.attachments as string[]), a.id],
                          }));
                        }}
                      />
                    </span>
                  )
                }
              />
            ) : f.type === "select" || f.type === "status" ? (
              <Select
                {...{ labId, projectId, f }}
                id={p.id}
                self={record?.id}
                value={v[f.name] as string}
                onChange={(x) => set(f.name, x)}
              />
            ) : (
              <Input
                {...p}
                maxLength={RESEARCH_MAX_LENGTH[f.name]}
                type={f.type === "date" ? "date" : f.type === "url" ? "url" : "text"}
                value={v[f.name] as string}
                onChange={(e) => set(f.name, e.target.value)}
              />
            )
          }
        </FormField>
      ))}
      {kind === "decisions" && (
        <ReferencesEditor rows={refs} errors={refErrors} onChange={setRefs} />
      )}
      {kind === "datasets" && (
        <ParticipantCheckbox checked={participant} onChange={setParticipant} />
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={save.isPending}>
          Save
        </Button>
      </div>
      {kind === "results" && (
        <UploadDialog
          open={uploading}
          onOpenChange={setUploading}
          send={async (file, onProgress) => {
            const a = await uploadFile.mutateAsync({ file, onProgress });
            await qc.invalidateQueries({ queryKey: root(labId) });
            setV((p) => ({ ...p, attachments: [...(p.attachments as string[]), a.id] }));
          }}
        />
      )}
    </form>
  );
}

const ANALYSIS_FIELD = FIELDS.results.find((f) => f.name === "analysis")!;

interface SetRow {
  key: number;
  title: string;
  summary: string;
  attachment?: { id: string; name: string };
}
const titleFrom = (filename: string) => filename.replace(/\.[^.]+$/, "");

/** Many results from one analysis, saved together: each figure becomes one result. */
export function ResultSetForm({
  labId,
  projectId,
  onDone,
  onCancel,
}: {
  labId: string;
  projectId: string;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [analysis, setAnalysis] = useState("");
  const [rows, setRows] = useState<SetRow[]>([]);
  const nextKey = useRef(0);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string>();
  const [uploading, setUploading] = useState(false);
  const { uploadFile } = useAttachments(labId, projectId);
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api(`/api/labs/${labId}/projects/${projectId}/results/set/`, { method: "POST", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: root(labId) }),
  });
  const patch = (key: number, change: Partial<SetRow>) =>
    setRows((all) => all.map((r) => (r.key === key ? { ...r, ...change } : r)));
  const addRow = (row: Omit<SetRow, "key">) => {
    const key = nextKey.current++;
    setRows((all) => [...all, { ...row, key }]);
  };

  function submit(ev: FormEvent) {
    ev.preventDefault();
    const errs: Record<string, string> = {};
    if (!analysis) errs.analysis = "Choose the analysis that produced these results";
    if (!rows.length) errs.rows = "Add at least one result";
    for (const r of rows) if (!r.title.trim()) errs[`title-${r.key}`] = "Enter a title";
    setErrors(errs);
    setFormError(undefined);
    if (Object.keys(errs).length) return;
    save.mutate(
      {
        analysis,
        items: rows.map((r) => ({
          title: r.title.trim(),
          summary: r.summary.trim(),
          attachments: r.attachment ? [r.attachment.id] : [],
        })),
      },
      {
        onSuccess: () => {
          toast.success(`Saved ${rows.length} ${rows.length === 1 ? "result" : "results"}`);
          onDone();
        },
        onError: (e) => {
          const { fields, form } = formErrors(e, ["analysis", "items"]);
          setErrors(fields);
          setFormError(form);
        },
      },
    );
  }

  return (
    <form onSubmit={submit} noValidate className="grid gap-4">
      <FormError message={formError} />
      <FormField
        label="Analysis that produced them"
        hint="Every result in this set comes from this analysis."
        error={errors.analysis}
      >
        {(p) => (
          <Select
            labId={labId}
            projectId={projectId}
            f={ANALYSIS_FIELD}
            id={p.id}
            value={analysis}
            onChange={setAnalysis}
          />
        )}
      </FormField>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => setUploading(true)}>
          <Upload aria-hidden /> Upload figures
        </Button>
        <FromDriveButton
          labId={labId}
          label="Figure from Drive"
          onPick={async (file) => {
            const a = await attachFromDrive(
              `/api/labs/${labId}/projects/${projectId}/attachments/`,
              file.id,
            );
            addRow({
              title: titleFrom(a.original_filename),
              summary: "",
              attachment: { id: a.id, name: a.original_filename },
            });
          }}
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => addRow({ title: "", summary: "" })}
        >
          <Plus aria-hidden /> Add a result without a file
        </Button>
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {errors.rows ?? "Each figure you upload becomes one result. You can edit the titles."}
        </p>
      ) : (
        <ul className="grid gap-3">
          {rows.map((r, i) => (
            <li key={r.key} className="grid gap-2 rounded-lg border p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="truncate text-xs text-muted-foreground">
                  {r.attachment?.name ?? "No file"}
                </p>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove result ${i + 1}`}
                  onClick={() => setRows((all) => all.filter((x) => x.key !== r.key))}
                >
                  <Trash2 aria-hidden />
                </Button>
              </div>
              <FormField label={`Title of result ${i + 1}`} error={errors[`title-${r.key}`]}>
                {(p) => (
                  <Input
                    {...p}
                    value={r.title}
                    maxLength={300}
                    onChange={(e) => patch(r.key, { title: e.target.value })}
                  />
                )}
              </FormField>
              <FormField label={`Summary of result ${i + 1} (optional)`}>
                {(p) => (
                  <Textarea
                    {...p}
                    rows={2}
                    value={r.summary}
                    onChange={(e) => patch(r.key, { summary: e.target.value })}
                  />
                )}
              </FormField>
            </li>
          ))}
        </ul>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={save.isPending}>
          Save all
        </Button>
      </div>
      <UploadDialog
        open={uploading}
        onOpenChange={setUploading}
        multiple
        send={async (file, onProgress) => {
          const a = await uploadFile.mutateAsync({ file, onProgress });
          addRow({
            title: titleFrom(a.original_filename),
            summary: "",
            attachment: { id: a.id, name: a.original_filename },
          });
        }}
      />
    </form>
  );
}

function Select({
  labId,
  projectId,
  f,
  id,
  self,
  value,
  onChange,
}: {
  labId: string;
  projectId: string;
  f: Field;
  id: string;
  self?: string;
  value: string;
  onChange: (v: string) => void;
}) {
  const opts = useOptions(labId, projectId, f.source ?? "datasets");
  const choices =
    f.type === "status"
      ? MANUSCRIPT_STATUSES.map(([id, label]) => ({ id, label }))
      : (opts.data ?? []).filter((o) => o.id !== self);
  return (
    <select id={id} className={selectCls} value={value} onChange={(e) => onChange(e.target.value)}>
      {f.type !== "status" && <option value="">{f.required ? "Choose one" : "None"}</option>}
      {choices.map((o) => (
        <option key={o.id} value={o.id}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

function Multi({
  labId,
  projectId,
  f,
  id,
  selected,
  onChange,
  extra,
}: {
  labId: string;
  projectId: string;
  f: Field;
  id: string;
  selected: string[];
  onChange: (v: string[]) => void;
  extra?: ReactNode;
}) {
  const opts = useOptions(labId, projectId, f.source!);
  return (
    <div id={id} role="group" aria-label={f.label} className="grid gap-1 rounded-md border p-2">
      {opts.data?.length === 0 && (
        <p className="text-xs text-muted-foreground">Nothing to pick yet.</p>
      )}
      {opts.data?.map((o) => (
        <label key={o.id} className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={selected.includes(o.id)}
            onChange={(e) =>
              onChange(e.target.checked ? [...selected, o.id] : selected.filter((x) => x !== o.id))
            }
          />
          {o.label}
        </label>
      ))}
      {extra}
    </div>
  );
}
