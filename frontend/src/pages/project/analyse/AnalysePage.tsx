import { BarChart3, Maximize2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { EmptyState } from "@/components/shared/EmptyState";
import { IconAction } from "@/components/shared/IconAction";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useFolders } from "@/hooks/documents";
import { downloadUrl, useAttachments } from "@/hooks/projects";
import { useRecords } from "@/hooks/research";
import type { Analysis, Attachment, Dataset, ResearchResult } from "@/lib/api-types";
import {
  TESTS,
  type DataShape,
  type EngineState,
  type LoadOptions,
  type ParamSpec,
  type ParamValues,
  type StatsEngine,
  type TestId,
  type TestSpec,
} from "@/lib/stats/contract";
import type { ProjectTabProps } from "@/pages/ProjectPage";
import { useDraftReport } from "@/pages/project/analyse/draft";
import { DataIssues } from "@/pages/project/analyse/DataIssues";
import { useGetEngine } from "@/pages/project/analyse/engine";
import { FocusShell } from "@/pages/project/analyse/FocusShell";
import { DataGrid } from "@/pages/project/analyse/DataGrid";
import { ResultCard, type Run } from "@/pages/project/analyse/ResultCard";
import { EngineStatus } from "@/pages/project/analyse/EngineStatus";
import { errorText, SAVED_MARK } from "@/pages/project/analyse/save";
import { StatsTabs, type ReportStatus, type TabInfo } from "@/pages/project/analyse/StatsTabs";
import { TestGuide } from "@/pages/project/analyse/TestGuide";

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
  /** How the file was read (the fixes chosen for it). */
  options?: LoadOptions;
}

interface Option {
  key: string;
  label: string;
  /** Why it can't be picked. */
  off?: "drive" | "grant";
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
  uid,
  spec,
  shape,
  value,
  error,
  onChange,
}: {
  /** Tells this report's fields from another report's, so each label finds its own field. */
  uid: string;
  spec: ParamSpec;
  shape: DataShape;
  value: ParamValues[string];
  error?: string;
  onChange: (v: ParamValues[string]) => void;
}) {
  const id = `param-${uid}-${spec.key}`;
  const numeric = shape.columns.filter((c) => c.kind === "numeric");
  let input: ReactNode;
  if (spec.kind === "numerics" || spec.kind === "columns") {
    const cols = spec.kind === "numerics" ? numeric : shape.columns;
    const chosen = Array.isArray(value) ? value : [];
    input = (
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {cols.map((c) => (
          <label
            key={c.name}
            className="flex min-w-0 items-center gap-2 text-sm [overflow-wrap:anywhere]"
          >
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
  } else if (spec.kind === "text") {
    input = (
      <Input
        id={id}
        value={typeof value === "string" ? value : ""}
        onChange={(e) => onChange(e.target.value || undefined)}
      />
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
      if (!p.optional)
        errs[p.key] =
          p.kind === "number"
            ? "Enter a number."
            : p.kind === "text"
              ? "Type a value."
              : "Choose a column.";
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

interface WorkspaceProps extends ProjectTabProps {
  tabId: string;
  active: boolean;
  /** The first report also answers the links from a dataset or file row. */
  primary: boolean;
  /** Which report's data the engine holds now: the engine reads one file at a time. */
  claim: { get: () => string | undefined; set: (id: string | undefined) => void };
  /** The tab strip, shown at the top of the workspace. */
  tabs: ReactNode;
  onInfo: (id: string, info: { title: string; status: ReportStatus }) => void;
}

function StatsWorkspace({
  labId,
  projectId,
  project,
  tabId,
  active,
  primary,
  claim,
  tabs,
  onInfo,
}: WorkspaceProps) {
  const { engine, failed } = useEngine();
  const [params, setParams] = useSearchParams();
  const focus = params.get("focus") === "1";
  const setFocus = (on: boolean) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (on) next.set("focus", "1");
        else next.delete("focus");
        return next;
      },
      { replace: true },
    );
  const files = useAttachments(labId, projectId).list;
  const datasets = useRecords<Dataset>(labId, projectId, "datasets");
  // A file in a marked folder counts as marked (as the server's is_flagged does), so results
  // drawn from it are saved marked too and stay away from AI tools.
  const folders = useFolders(labId, projectId);
  const markedFolders = new Set(
    (folders.data ?? []).filter((f) => f.contains_participant_data).map((f) => f.id),
  );
  const analyses = useRecords<Analysis>(labId, projectId, "analyses");
  const results = useRecords<ResearchResult>(labId, projectId, "results");
  const canSave = project.my_permissions.includes("edit_content") && project.status !== "archived";
  const canExport = project.my_permissions.includes("export");

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
  // D244: grant letters are PI-only; results saved from one would be visible to the whole lab.
  const why = (f: Attachment): Option["off"] =>
    f.pi_only ? "grant" : isGoogle(f) ? "drive" : undefined;
  // Workbooks that Statistics saved (attached to a result of an analysis it made) are not data.
  const statsAnalyses = new Set(
    (analyses.data ?? []).filter((a) => a.description.includes(SAVED_MARK)).map((a) => a.id),
  );
  const savedOutputs = new Set(
    (results.data ?? [])
      .filter((r) => statsAnalyses.has(r.analysis.id))
      .flatMap((r) => r.attachments.map((x) => x.id)),
  );
  const options: Option[] = [
    ...fileList
      .filter(
        (f) =>
          !savedOutputs.has(f.id) &&
          (TABULAR.test(f.original_filename) ||
            (isGoogle(f) && /sheet|csv|excel/i.test(f.content_type))),
      )
      .map((f) => ({
        key: `file:${f.id}`,
        label: f.original_filename,
        off: why(f),
      })),
    ...(datasets.data ?? [])
      .filter((d) => d.data_file)
      .map((d) => {
        const att = byId.get(d.data_file!.id);
        return {
          key: `dataset:${d.id}`,
          label: `${d.name} (dataset)`,
          off: !att
            ? "drive"
            : (why(att) ?? (TABULAR.test(att.original_filename) ? undefined : "drive")),
        };
      }),
  ];
  const googleLinked = options.some((o) => o.off === "drive");
  const grantFiles = options.some((o) => o.off === "grant");

  async function start(src: Source) {
    if (!engine) return;
    setLoading(true);
    setLoadError(undefined);
    setShape(undefined);
    try {
      // load() moves the bytes into the worker; keep our own copy for a later sheet change
      const s = await engine.load({ name: src.name, bytes: src.bytes.slice(0) });
      claim.set(tabId);
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
    // A file in a folder is marked if the folder is; without the folder list, ask when saving.
    const marked =
      att.contains_participant_data ||
      !!ds?.contains_participant_data ||
      (!!att.folder && markedFolders.has(att.folder));
    try {
      // stream=1: the bytes come from this site, never a storage redirect fetch() can't follow
      const res = await fetch(`${downloadUrl(labId, att.id)}?stream=1`, {
        credentials: "same-origin",
      });
      if (!res.ok) throw new Error("Could not download that file.");
      await start({
        name: att.original_filename,
        bytes: await res.arrayBuffer(),
        datasetId: ds?.id,
        flagged: marked ? true : att.folder && !folders.data ? null : false,
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

  // A new sheet starts with no options; a fix from DataIssues reloads the same sheet with its own.
  async function chooseSheet(sheet: string | undefined, options: LoadOptions = {}) {
    if (!engine || !source) return;
    setLoading(true);
    setLoadError(undefined);
    try {
      const s = await engine.load(
        { name: source.name, bytes: source.bytes.slice(0), sheet },
        options,
      );
      claim.set(tabId);
      setSource({ ...source, options });
      setShape(s);
    } catch (e) {
      setLoadError(errorText(e));
    } finally {
      setLoading(false);
    }
  }

  const reloadTicket = useRef(0);
  // Another report may have loaded its file since this one was last in front: read ours again.
  useEffect(() => {
    if (!active || !engine || !source || !shape || claim.get() === tabId) return;
    const ticket = ++reloadTicket.current;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    engine
      .load(
        { name: source.name, bytes: source.bytes.slice(0), sheet: shape.sheet ?? undefined },
        source.options,
      )
      .then(() => claim.set(tabId))
      .catch((e) => ticket === reloadTicket.current && setLoadError(errorText(e)))
      .finally(() => ticket === reloadTicket.current && setLoading(false));
    return () => {
      reloadTicket.current++;
    };
    // only when this report comes to the front
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  // The links from a dataset row or a file row: pick once the lists (folders too, for the
  // participant mark) have arrived.
  const deepLinked = useRef(false);
  const foldersSettled = !!folders.data || folders.isError;
  useEffect(() => {
    if (
      !primary ||
      deepLinked.current ||
      !engine ||
      !files.data ||
      !datasets.data ||
      !foldersSettled
    )
      return;
    const key = params.get("dataset")
      ? `dataset:${params.get("dataset")}`
      : params.get("file")
        ? `file:${params.get("file")}`
        : "";
    deepLinked.current = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (key && options.some((o) => o.key === key && !o.off)) void choose(key);
    // once, when everything has arrived: choose() and options are rebuilt on every render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engine, files.data, datasets.data, foldersSettled]);

  // ---- test
  const [testId, setTestId] = useState("");
  const test = TESTS.find((t) => t.id === testId);
  const [values, setValues] = useState<ParamValues>({});
  const [tried, setTried] = useState(false);
  const [runError, setRunError] = useState<string>();
  const [runs, setRuns] = useState<Run[]>([]);
  const nextId = useRef(1);
  const newest = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!runs.length) return;
    const calm = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    newest.current?.scrollIntoView?.({ behavior: calm ? "auto" : "smooth", block: "start" });
  }, [runs.length]);
  const busy = state.state === "running" || state.state === "loading";
  const errors = test ? validate(test, values) : {};

  // Live mode: the result follows the options, like a spreadsheet. "Keep" pins it to the list.
  const [live, setLive] = useState(false);
  const [preview, setPreview] = useState<Run>();
  const [previewError, setPreviewError] = useState<string>();
  const previewTicket = useRef(0);
  const valuesKey = JSON.stringify(values);
  const hasErrors = test ? Object.keys(validate(test, values)).length > 0 : true;
  useEffect(() => {
    if (!active || !live || !engine || !test || !source || hasErrors) return;
    const ticket = ++previewTicket.current;
    const timer = setTimeout(() => {
      const clean = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== undefined));
      engine
        .run({ test: test.id, params: clean })
        .then((result) => {
          if (ticket !== previewTicket.current) return;
          setPreviewError(undefined);
          setPreview({
            id: 0,
            result,
            inputName: source.name,
            datasetId: source.datasetId,
            flagged: source.flagged,
          });
        })
        .catch((e) => ticket === previewTicket.current && setPreviewError(errorText(e)));
    }, 400);
    return () => clearTimeout(timer);
    // `values` is covered by valuesKey; the rest are the inputs of the run
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, live, engine, test, source, hasErrors, valuesKey]);
  function keepPreview() {
    if (!preview) return;
    setRuns((r) => [{ ...preview, id: nextId.current++ }, ...r]);
    setPreview(undefined);
  }

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

  // The report is kept in the project's Analysis list from the moment a test is chosen, until the
  // first result is saved (ResultCard then finishes the same record). Data that may identify
  // participants is never kept without the user's say-so, so those reports are saved by hand.
  const draft = useDraftReport({
    labId,
    projectId,
    enabled: canSave && !!test && source?.flagged === false && runs.length === 0,
    title: source?.name ?? "Statistics",
    testLabel: test?.label ?? "",
    inputName: source?.name ?? "",
    datasetId: source?.datasetId,
    options: values,
  });
  const autoSave = canSave ? { draftId: draft.draftId } : undefined;
  const unsavedRuns = runs.some((r) => !r.saved);
  const status: ReportStatus = runs.length
    ? unsavedRuns
      ? "unsaved"
      : "saved"
    : draft.state === "saved" || draft.state === "saving"
      ? "progress"
      : "new";
  const tabTitle = shape ? `${test ? `${test.label} · ` : ""}${shape.fileName}` : "New report";
  useEffect(() => {
    onInfo(tabId, { title: tabTitle, status });
  }, [onInfo, tabId, tabTitle, status]);

  const groups = [...new Set(TESTS.map((t) => t.group))].map((g) => ({
    g,
    tests: TESTS.filter((t) => t.group === g),
  }));

  function pickTest(t: TestSpec) {
    setTestId(t.id);
    engine?.prepare(t.id); // fetch the test's packages while the columns are being picked
    const v = defaults(t);
    // "Split by" is easy to miss: when one column is an obvious grouping, fill it in
    if (t.id === "normality" && shape) {
      const cats = shape.columns.filter(
        (c) => c.kind === "categorical" && c.distinct >= 2 && c.distinct <= 10,
      );
      if (cats.length === 1) v.group = cats[0]!.name;
    }
    setValues(v);
    setTried(false);
    setPreview(undefined);
    setPreviewError(undefined);
  }
  function pickTestId(id: TestId) {
    const t = TESTS.find((x) => x.id === id);
    if (t) pickTest(t);
  }

  const messages = (
    <>
      {failed && (
        <p role="alert" className="text-sm font-medium text-destructive">
          {failed}
        </p>
      )}
      {!focus && <EngineStatus state={state} testId={testId} />}
      {state.state === "error" && !focus && (
        <p role="alert" className="text-sm font-medium text-destructive">
          {state.message}
        </p>
      )}
      {(runError || previewError) && (
        <p role="alert" className="text-sm font-medium text-destructive">
          {runError ?? previewError}
        </p>
      )}
    </>
  );

  const picker = (
    <div className="grid gap-3">
      {options.length === 0 && !source && files.isFetched && datasets.isFetched && (
        <EmptyState
          icon={BarChart3}
          title="No data files in this project yet"
          description="Choose a file from this computer below, or upload a CSV or Excel file to the project."
        />
      )}
      <div className="grid max-w-3xl gap-3 sm:grid-cols-2">
        {options.length > 0 && (
          <div className="grid gap-1.5">
            <label htmlFor={`data-pick-${tabId}`} className="text-sm font-medium">
              From this project
            </label>
            <select
              id={`data-pick-${tabId}`}
              className={SELECT}
              value={picked}
              onChange={(e) => void choose(e.target.value)}
            >
              <option value="">Choose a file or dataset</option>
              {options.map((o) => (
                <option key={o.key} value={o.key} disabled={!!o.off}>
                  {o.label}
                  {o.off === "drive"
                    ? " (in Google Drive)"
                    : o.off === "grant"
                      ? " (grant file)"
                      : ""}
                </option>
              ))}
            </select>
            {googleLinked && (
              <p className="text-xs text-muted-foreground">
                Files in Google Drive cannot be read here. Download it from Google Drive, then
                choose From this computer.
              </p>
            )}
            {grantFiles && (
              <p className="text-xs text-muted-foreground">
                Grant files can&apos;t be analysed here.
              </p>
            )}
          </div>
        )}
        <div className="grid gap-1.5">
          <label htmlFor={`data-local-${tabId}`} className="text-sm font-medium">
            From this computer
          </label>
          <input
            id={`data-local-${tabId}`}
            type="file"
            accept=".csv,.tsv,.txt,.xlsx"
            onChange={(e) => void chooseLocal(e.target.files?.[0])}
            className="text-sm text-muted-foreground file:mr-3 file:rounded-md file:border file:border-input file:bg-background file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-foreground hover:file:bg-accent"
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
    </div>
  );

  const optionsPanel =
    test && shape ? (
      <section aria-label="Options" className="grid gap-4 rounded-xl border bg-card p-4">
        <div>
          <h3 className="font-semibold">{test.label}</h3>
          <p className="text-xs text-muted-foreground">{test.help}</p>
        </div>
        <div className={cn("grid gap-4", focus && "md:grid-cols-2 xl:grid-cols-3")}>
          {test.params.map((p) => (
            <ParamField
              uid={tabId}
              key={`${test.id}-${p.key}`}
              spec={p}
              shape={shape}
              value={values[p.key]}
              error={tried ? errors[p.key] : undefined}
              onChange={(v) => setValues((cur) => ({ ...cur, [p.key]: v }))}
            />
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={live}
            onChange={(e) => {
              setLive(e.target.checked);
              if (!e.target.checked) setPreview(undefined);
            }}
          />
          Update results as I change options
        </label>
        <div className="flex items-center gap-3">
          <Button onClick={() => void run()} disabled={busy || loading}>
            Run
          </Button>
        </div>
      </section>
    ) : null;

  const dataBlock =
    shape && engine ? (
      <section aria-label="Your data" className="grid gap-2">
        <p className="text-sm">
          <span className="font-medium">{shape.fileName}</span>: {shape.rows} rows,{" "}
          {shape.columns.length} columns
        </p>
        <DataIssues
          issues={shape.issues}
          busy={loading}
          onFix={(fix) => void chooseSheet(shape.sheet ?? undefined, fix)}
        />
        {shape.sheets.length > 1 && (
          <div className="grid max-w-xs gap-1.5">
            <label htmlFor={`sheet-pick-${tabId}`} className="text-sm font-medium">
              Sheet
            </label>
            <select
              id={`sheet-pick-${tabId}`}
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
        <DataGrid engine={engine} shape={shape} tall={focus} />
      </section>
    ) : null;

  const resultsBlock =
    preview || runs.length > 0 ? (
      <Section title="Results">
        {preview && (
          <div className="grid gap-2">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs text-muted-foreground">
                Live result. It changes when you change the options.
              </p>
              <Button size="sm" variant="outline" onClick={keepPreview}>
                Keep this result
              </Button>
            </div>
            <ResultCard
              run={preview}
              labId={labId}
              projectId={projectId}
              canSave={false}
              canExport={canExport}
              onSaved={() => {}}
            />
          </div>
        )}
        {runs.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Earlier runs from this visit stay here so you can compare. They are gone when you leave
            the page unless you save them.
          </p>
        )}
        {runs.map((r, i) => (
          <div key={r.id} ref={i === 0 ? newest : undefined} className="scroll-mt-24">
            <ResultCard
              run={r}
              labId={labId}
              projectId={projectId}
              canSave={canSave}
              canExport={canExport}
              autoSave={autoSave}
              onSaved={(saved) =>
                setRuns((all) => all.map((x) => (x.id === r.id ? { ...x, saved } : x)))
              }
              onRemove={() => setRuns((all) => all.filter((x) => x.id !== r.id))}
            />
          </div>
        ))}
      </Section>
    ) : null;

  if (focus) {
    if (!active) return null;
    return (
      <FocusShell
        tabs={tabs}
        projectId={projectId}
        title={shape ? shape.fileName : "Statistics"}
        engineState={state}
        groups={groups}
        testId={testId}
        onPick={pickTest}
        picker={picker}
        needsData={!shape}
        data={dataBlock}
        options={optionsPanel}
        results={resultsBlock}
        messages={messages}
        onExit={() => setFocus(false)}
      />
    );
  }

  return (
    <div
      hidden={!active}
      role="tabpanel"
      id={`report-panel-${tabId}`}
      aria-labelledby={`report-tab-${tabId}`}
      className="grid gap-6 pb-8"
    >
      <PageHeader
        title="Statistics"
        description="Runs on your computer. Your data is not sent anywhere unless you save it."
        actions={
          <IconAction
            label="Focus mode"
            icon={<Maximize2 aria-hidden />}
            variant="outline"
            onClick={() => setFocus(true)}
          />
        }
      />
      {tabs}
      {draft.state === "error" && (
        <p role="alert" className="text-sm font-medium text-destructive">
          Could not keep this report in the project&apos;s Analysis list: {draft.error}
        </p>
      )}
      {messages}

      <Section title={shape ? "Data" : "1. Choose your data"}>{picker}</Section>

      {shape && engine && (
        <div className="grid items-start gap-6 xl:grid-cols-[22rem_minmax(0,1fr)]">
          <aside aria-label="Analysis" className="grid gap-4 xl:sticky xl:top-4">
            <div className="grid gap-3">
              {groups.map(({ g, tests }) => (
                <div key={g} role="group" aria-label={g} className="grid gap-1.5">
                  <h3 className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    {g}
                  </h3>
                  <div className="flex flex-wrap gap-1.5">
                    {tests.map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        aria-pressed={testId === t.id}
                        title={t.help}
                        onClick={() => pickTest(t)}
                        className={cn(
                          "glass-field rounded-lg px-2.5 py-1.5 text-sm hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                          testId === t.id && "border-primary bg-primary/10 font-medium",
                        )}
                      >
                        {t.label}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <TestGuide onPick={pickTestId} />
            {optionsPanel ?? (
              <p className="text-sm text-muted-foreground">
                Choose an analysis to see its options.
              </p>
            )}
          </aside>
          <div className="grid min-w-0 gap-6">
            {dataBlock}
            {resultsBlock}
          </div>
        </div>
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

/**
 * Statistics: one tab per report, like browser tabs. Each tab keeps its own data, test, options and
 * results; the engine holds one file at a time, so a tab reads its file again when it comes back to
 * the front. Reports are kept in the project's Analysis list while in progress and when finished.
 */
export default function AnalysePage(props: ProjectTabProps) {
  const [tabs, setTabs] = useState<string[]>(["r1"]);
  const [activeId, setActiveId] = useState("r1");
  const [info, setInfo] = useState<Record<string, Omit<TabInfo, "id">>>({});
  const claimed = useRef<string>();
  const claim = useMemo(
    () => ({
      get: () => claimed.current,
      set: (id: string | undefined) => {
        claimed.current = id;
      },
    }),
    [],
  );
  const counter = useRef(2);

  const onInfo = useMemo(
    () => (id: string, i: Omit<TabInfo, "id">) =>
      setInfo((m) =>
        m[id]?.title === i.title && m[id]?.status === i.status ? m : { ...m, [id]: i },
      ),
    [],
  );
  const add = () => {
    const id = `r${counter.current++}`;
    setTabs((t) => [...t, id]);
    setActiveId(id);
  };
  const close = (id: string) => {
    if (
      info[id]?.status === "unsaved" &&
      !window.confirm("This report has results that are not saved. Close it anyway?")
    )
      return;
    if (claim.get() === id) claim.set(undefined);
    setInfo((m) => Object.fromEntries(Object.entries(m).filter(([k]) => k !== id)));
    if (tabs.length === 1) {
      const fresh = `r${counter.current++}`;
      setTabs([fresh]);
      setActiveId(fresh);
      return;
    }
    const i = tabs.indexOf(id);
    const rest = tabs.filter((t) => t !== id);
    setTabs(rest);
    if (activeId === id) setActiveId(rest[Math.min(i, rest.length - 1)]!);
  };

  const strip = (
    <StatsTabs
      tabs={tabs.map((id) => ({
        id,
        title: info[id]?.title ?? "New report",
        status: info[id]?.status ?? "new",
      }))}
      activeId={activeId}
      onSelect={setActiveId}
      onNew={add}
      onClose={close}
    />
  );

  return (
    <>
      {tabs.map((id, i) => (
        <StatsWorkspace
          key={id}
          {...props}
          tabId={id}
          active={id === activeId}
          primary={i === 0 && id === "r1"}
          claim={claim}
          tabs={strip}
          onInfo={onInfo}
        />
      ))}
    </>
  );
}
