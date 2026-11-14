import { BarChart3 } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { downloadUrl, useAttachments } from "@/hooks/projects";
import { useRecords } from "@/hooks/research";
import type { Attachment, Dataset } from "@/lib/api-types";
import {
  TESTS,
  type DataShape,
  type EngineState,
  type ParamSpec,
  type ParamValues,
  type StatsEngine,
  type TestSpec,
} from "@/lib/stats/contract";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { useGetEngine } from "@/pages/project/analyse/engine";
import { ResultCard, type Run } from "@/pages/project/analyse/ResultCard";
import { errorText } from "@/pages/project/analyse/save";

const SELECT =
  "h-9 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-2 focus-visible:outline-ring";
const TABULAR = /\.(csv|tsv|txt|xlsx)$/i;
const isGoogle = (a: Pick<Attachment, "drive_file_id" | "external_url">) =>
  !!a.drive_file_id || !!a.external_url;

interface Source {
  name: string;
  bytes: ArrayBuffer;
  datasetId?: string;
  flagged: boolean | null;
}

interface Option {
  key: string;
  label: string;
  disabled: boolean;
}

function useEngine(): { engine?: StatsEngine; failed?: string } {
  const get = useGetEngine();
  return useMemo(() => {
    try {
      return { engine: get() };
    } catch (e) {
      return { failed: errorText(e) };
    }
  }, [get]);
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="grid gap-3">
      <h2 className="text-base font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function ParamField({
  spec,
  shape,
  value,
  error,
  onChange,
}: {
  spec: ParamSpec;
  shape: DataShape;
  value: ParamValues[string];
  error?: string;
  onChange: (v: ParamValues[string]) => void;
}) {
  const id = `param-${spec.key}`;
  const numeric = shape.columns.filter((c) => c.kind === "numeric");
  let input: ReactNode;
  if (spec.kind === "numerics" || spec.kind === "columns") {
    const cols = spec.kind === "numerics" ? numeric : shape.columns;
    const chosen = Array.isArray(value) ? value : [];
    input = (
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {cols.map((c) => (
          <label key={c.name} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={chosen.includes(c.name)}
              onChange={(e) =>
                onChange(
                  e.target.checked ? [...chosen, c.name] : chosen.filter((n) => n !== c.name),
                )
              }
            />
            {c.name}
          </label>
        ))}
        {!cols.length && <p className="text-sm text-muted-foreground">No suitable columns.</p>}
      </div>
    );
  } else if (spec.kind === "number") {
    input = (
      <Input
        id={id}
        type="number"
        step="any"
        value={typeof value === "number" ? value : ""}
        onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))}
      />
    );
  } else {
    const opts =
      spec.kind === "choice"
        ? (spec.options ?? []).map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))
        : spec.kind === "numeric"
          ? numeric.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name}
              </option>
            ))
          : [
              <optgroup key="g" label="Categories">
                {shape.columns
                  .filter((c) => c.kind === "categorical")
                  .map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name}
                    </option>
                  ))}
              </optgroup>,
              <optgroup key="o" label="Other columns">
                {shape.columns
                  .filter((c) => c.kind !== "categorical")
                  .map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.name}
                    </option>
                  ))}
              </optgroup>,
            ];
    input = (
      <select
        id={id}
        className={SELECT}
        value={typeof value === "string" ? value : ""}
        onChange={(e) => onChange(e.target.value || undefined)}
      >
        <option value="">{spec.optional ? "None" : "Choose"}</option>
        {opts}
      </select>
    );
  }
  const multi = spec.kind === "numerics" || spec.kind === "columns";
  const Wrap = multi ? "fieldset" : "div";
  return (
    <Wrap className="grid gap-1.5">
      {multi ? (
        <legend className="mb-1 text-sm font-medium">{spec.label}</legend>
      ) : (
        <label htmlFor={id} className="text-sm font-medium">
          {spec.label}
          {spec.optional && <span className="font-normal text-muted-foreground"> (optional)</span>}
        </label>
      )}
      {input}
      {spec.help && <p className="text-xs text-muted-foreground">{spec.help}</p>}
      {error && (
        <p role="alert" className="text-sm font-medium text-destructive">
          {error}
        </p>
      )}
    </Wrap>
  );
}

function validate(test: TestSpec, v: ParamValues): Record<string, string> {
  const errs: Record<string, string> = {};
  for (const p of test.params) {
    const x = v[p.key];
    const empty = x === undefined || x === "" || (Array.isArray(x) && !x.length);
    if (empty) {
      if (!p.optional) errs[p.key] = p.kind === "number" ? "Enter a number." : "Choose a column.";
    } else if (Array.isArray(x) && x.length < (p.min ?? 1)) {
      errs[p.key] = `Choose at least ${p.min}.`;
    }
  }
  return errs;
}

const defaults = (t: TestSpec): ParamValues =>
  Object.fromEntries(
    t.params.filter((p) => p.default !== undefined).map((p) => [p.key, p.default]),
  );

export default function AnalysePage({ labId, projectId, project }: ProjectTabProps) {
  const { engine, failed } = useEngine();
  const [params] = useSearchParams();
  const files = useAttachments(labId, projectId).list;
  const datasets = useRecords<Dataset>(labId, projectId, "datasets");
  const canSave = project.my_permissions.includes("edit_content") && project.status !== "archived";

  const [state, setState] = useState<EngineState>({ state: "idle" });
  useEffect(() => {
    if (!engine) return;
    const off = engine.subscribe(setState);
    engine.warmUp();
    return off;
  }, [engine]);

  // ---- data
  const [picked, setPicked] = useState("");
  const [source, setSource] = useState<Source>();
  const [shape, setShape] = useState<DataShape>();
  const [loadError, setLoadError] = useState<string>();
  const [loading, setLoading] = useState(false);

  const fileList = files.data ?? [];
  const byId = new Map(fileList.map((f) => [f.id, f]));
  const options: Option[] = [
    ...fileList
      .filter(
        (f) =>
          TABULAR.test(f.original_filename) ||
          (isGoogle(f) && /sheet|csv|excel/i.test(f.content_type)),
      )
      .map((f) => ({
        key: `file:${f.id}`,
        label: f.original_filename,
        disabled: isGoogle(f),
      })),
    ...(datasets.data ?? [])
      .filter((d) => d.data_file)
      .map((d) => {
        const att = byId.get(d.data_file!.id);
        return {
          key: `dataset:${d.id}`,
          label: `${d.name} (dataset)`,
          disabled: !att || isGoogle(att) || !TABULAR.test(att.original_filename),
        };
      }),
  ];
  const googleLinked = options.some((o) => o.disabled);

  async function start(src: Source) {
    if (!engine) return;
    setLoading(true);
    setLoadError(undefined);
    setShape(undefined);
    try {
      const s = await engine.load({ name: src.name, bytes: src.bytes });
      setSource(src);
      setShape(s);
    } catch (e) {
      setLoadError(errorText(e));
    } finally {
      setLoading(false);
    }
  }

  async function choose(key: string) {
    setPicked(key);
    if (!key) return;
    const [kind, id] = key.split(":") as [string, string];
    const ds = kind === "dataset" ? datasets.data?.find((d) => d.id === id) : undefined;
    const att = byId.get(kind === "dataset" ? (ds?.data_file?.id ?? "") : id);
    if (!att) return;
    setLoading(true);
    setLoadError(undefined);
    setShape(undefined);
    try {
      const res = await fetch(downloadUrl(labId, att.id), { credentials: "same-origin" });
      if (!res.ok) throw new Error("Could not download that file.");
      await start({
        name: att.original_filename,
        bytes: await res.arrayBuffer(),
        datasetId: ds?.id,
        flagged: att.contains_participant_data || !!ds?.contains_participant_data,
      });
    } catch (e) {
      setLoadError(errorText(e));
      setLoading(false);
    }
  }

  async function chooseLocal(file: File | undefined) {
    if (!file) return;
    setPicked("");
    await start({ name: file.name, bytes: await file.arrayBuffer(), flagged: null });
  }

  async function chooseSheet(sheet: string) {
    if (!engine || !source) return;
    setLoading(true);
    try {
      setShape(await engine.load({ name: source.name, bytes: source.bytes, sheet }));
    } catch (e) {
      setLoadError(errorText(e));
    } finally {
      setLoading(false);
    }
  }

  // The links from a dataset row or a file row: pick once the lists have arrived.
  const deepLinked = useRef(false);
  useEffect(() => {
    if (deepLinked.current || !engine || !files.data || !datasets.data) return;
    const key = params.get("dataset")
      ? `dataset:${params.get("dataset")}`
      : params.get("file")
        ? `file:${params.get("file")}`
        : "";
    deepLinked.current = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect, react-hooks/exhaustive-deps
    if (key && options.some((o) => o.key === key && !o.disabled)) void choose(key);
  }, [engine, files.data, datasets.data]);

  // ---- test
  const [testId, setTestId] = useState("");
  const test = TESTS.find((t) => t.id === testId);
  const [values, setValues] = useState<ParamValues>({});
  const [tried, setTried] = useState(false);
  const [runError, setRunError] = useState<string>();
  const [runs, setRuns] = useState<Run[]>([]);
  const nextId = useRef(1);
  const busy = state.state === "running" || state.state === "loading";
  const errors = test ? validate(test, values) : {};

  async function run() {
    if (!engine || !test || !source) return;
    setTried(true);
    if (Object.keys(errors).length) return;
    setRunError(undefined);
    try {
      const clean = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== undefined));
      const result = await engine.run({ test: test.id, params: clean });
      setRuns((r) => [
        {
          id: nextId.current++,
          result,
          inputName: source.name,
          datasetId: source.datasetId,
          flagged: source.flagged,
        },
        ...r,
      ]);
    } catch (e) {
      setRunError(errorText(e));
    }
  }

  const groups = (["Describe", "Compare groups", "Relationships"] as const).map((g) => ({
    g,
    tests: TESTS.filter((t) => t.group === g),
  }));

  return (
    <div className="grid gap-8">
      <PageHeader
        title="Statistics"
        description="Runs on your computer. Your data is not sent anywhere unless you save it."
      />
      {failed && (
        <p role="alert" className="text-sm font-medium text-destructive">
          {failed}
        </p>
      )}

      <Section title="1. Choose your data">
        {options.length === 0 && files.isFetched && datasets.isFetched && (
          <EmptyState
            icon={BarChart3}
            title="No data files in this project yet"
            description="Choose a file from this computer below, or upload a CSV or Excel file to the project."
          />
        )}
        <div className="grid max-w-xl gap-3">
          {options.length > 0 && (
            <div className="grid gap-1.5">
              <label htmlFor="data-pick" className="text-sm font-medium">
                From this project
              </label>
              <select
                id="data-pick"
                className={SELECT}
                value={picked}
                onChange={(e) => void choose(e.target.value)}
              >
                <option value="">Choose a file or dataset</option>
                {options.map((o) => (
                  <option key={o.key} value={o.key} disabled={o.disabled}>
                    {o.label}
                    {o.disabled ? " (in Google Drive)" : ""}
                  </option>
                ))}
              </select>
              {googleLinked && (
                <p className="text-xs text-muted-foreground">
                  Files in Google Drive cannot be read here. Download it from Google Drive, then
                  choose From this computer.
                </p>
              )}
            </div>
          )}
          <div className="grid gap-1.5">
            <label htmlFor="data-local" className="text-sm font-medium">
              From this computer
            </label>
            <input
              id="data-local"
              type="file"
              accept=".csv,.tsv,.txt,.xlsx"
              onChange={(e) => void chooseLocal(e.target.files?.[0])}
              className="text-sm"
            />
            <p className="text-xs text-muted-foreground">
              This file is read on your computer and is never uploaded.
            </p>
          </div>
        </div>
        {loading && <Skeleton className="h-4 w-64" aria-label="Reading the file" />}
        {loadError && (
          <p role="alert" className="text-sm font-medium text-destructive">
            {loadError}
          </p>
        )}
        {shape && (
          <div className="grid gap-3">
            {shape.sheets.length > 1 && (
              <div className="grid max-w-xs gap-1.5">
                <label htmlFor="sheet-pick" className="text-sm font-medium">
                  Sheet
                </label>
                <select
                  id="sheet-pick"
                  className={SELECT}
                  value={shape.sheet ?? ""}
                  onChange={(e) => void chooseSheet(e.target.value)}
                >
                  {shape.sheets.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </div>
            )}
            <p className="text-sm">
              <span className="font-medium">{shape.fileName}</span>: {shape.rows} rows,{" "}
              {shape.columns.length} columns
            </p>
            <div className="overflow-x-auto">
              <Table>
                <caption className="sr-only">Columns in the file</caption>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">Column</TableHead>
                    <TableHead scope="col">Type</TableHead>
                    <TableHead scope="col">Missing</TableHead>
                    <TableHead scope="col">Examples</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {shape.columns.map((c) => (
                    <TableRow key={c.name}>
                      <TableCell>{c.name}</TableCell>
                      <TableCell>{c.kind === "categorical" ? "category" : c.kind}</TableCell>
                      <TableCell>{c.missing}</TableCell>
                      <TableCell>{c.sample.map((s) => s ?? "(empty)").join(", ")}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )}
      </Section>

      {shape && (
        <Section title="2. Choose a test">
          <div className="grid max-w-xl gap-4">
            <div className="grid gap-1.5">
              <label htmlFor="test-pick" className="text-sm font-medium">
                Test
              </label>
              <select
                id="test-pick"
                className={SELECT}
                value={testId}
                onChange={(e) => {
                  setTestId(e.target.value);
                  const t = TESTS.find((x) => x.id === e.target.value);
                  setValues(t ? defaults(t) : {});
                  setTried(false);
                }}
              >
                <option value="">Choose a test</option>
                {groups.map(({ g, tests }) => (
                  <optgroup key={g} label={g}>
                    {tests.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.label}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
              {test && <p className="text-xs text-muted-foreground">{test.help}</p>}
            </div>
            {test?.params.map((p) => (
              <ParamField
                key={`${test.id}-${p.key}`}
                spec={p}
                shape={shape}
                value={values[p.key]}
                error={tried ? errors[p.key] : undefined}
                onChange={(v) => setValues((cur) => ({ ...cur, [p.key]: v }))}
              />
            ))}
            {test && (
              <div className="flex items-center gap-3">
                <Button onClick={() => void run()} disabled={busy}>
                  Run
                </Button>
              </div>
            )}
          </div>
        </Section>
      )}

      {(state.state === "loading" || state.state === "running") && (
        <div role="status" className="grid gap-2">
          <Skeleton className="h-2 w-64" />
          <p className="text-sm text-muted-foreground">{state.message}</p>
        </div>
      )}
      {state.state === "error" && (
        <p role="alert" className="text-sm font-medium text-destructive">
          {state.message}
        </p>
      )}
      {runError && (
        <p role="alert" className="text-sm font-medium text-destructive">
          {runError}
        </p>
      )}

      {runs.length > 0 && (
        <Section title="Results">
          <p className="text-xs text-muted-foreground">
            Earlier runs from this visit stay here so you can compare. They are gone when you leave
            the page unless you save them.
          </p>
          {runs.map((r) => (
            <ResultCard
              key={r.id}
              run={r}
              labId={labId}
              projectId={projectId}
              canSave={canSave}
              onSaved={(saved) =>
                setRuns((all) => all.map((x) => (x.id === r.id ? { ...x, saved } : x)))
              }
            />
          ))}
        </Section>
      )}
      {!shape && (
        <p className="text-sm text-muted-foreground">
          <Link
            className="text-primary hover:underline"
            to={`/labs/${labId}/projects/${projectId}/documents`}
          >
            Upload a file to this project
          </Link>{" "}
          to analyse it here later.
        </p>
      )}
    </div>
  );
}
