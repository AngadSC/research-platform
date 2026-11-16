/// <reference lib="webworker" />
/**
 * The statistics worker: Pyodide (Python compiled to WebAssembly) running stats.py, off the main
 * thread. Pyodide and its packages are served from our own origin under /pyodide/v<version>/
 * (scripts/fetch-pyodide.mjs puts them there). Jobs run one at a time, in the order they arrive.
 */
import { loadPyodide, version, type PyodideInterface } from "pyodide";
import type { EngineState, LoadOptions } from "@/lib/stats/contract";
import source from "@/lib/stats/stats.py?raw";

export type Job =
  | { id: number; type: "warmup" }
  | {
      id: number;
      type: "load";
      name: string;
      bytes: ArrayBuffer;
      sheet?: string;
      options?: LoadOptions;
    }
  | { id: number; type: "run"; test: string; params: Record<string, unknown> }
  | { id: number; type: "prepare"; test: string }
  | { id: number; type: "rows"; offset: number; limit: number }
  | { id: number; type: "table_xlsx"; context: Record<string, unknown>; table: unknown };

export type Reply =
  | { type: "state"; state: EngineState }
  | { type: "done"; id: number; value: unknown }
  | { type: "fail"; id: number; message: string };

declare const self: DedicatedWorkerGlobalScope;

const FIRST_LOAD = "Getting the statistics tools ready (first time only)";
const COULD_NOT_LOAD =
  "The statistics tools could not be loaded. Check your connection and try again.";
const BLOCKED =
  "This browser blocked the statistics tools from starting. Try an up-to-date Chrome, Edge, Firefox or Safari.";

let python: Promise<PyodideInterface> | null = null;
let queue: Promise<void> = Promise.resolve();
let waiting = 0;

function post(reply: Reply, transfer: Transferable[] = []) {
  self.postMessage(reply, { transfer });
}

function setState(state: EngineState) {
  post({ type: "state", state });
}

function getPython(): Promise<PyodideInterface> {
  python ??= (async () => {
    setState({ state: "loading", message: FIRST_LOAD });
    // If WebAssembly is blocked (a security policy, or a browser setting), Pyodide would hang
    // instead of failing, so try the smallest possible module first.
    try {
      new WebAssembly.Module(new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0]));
    } catch {
      throw new Error(BLOCKED);
    }
    const py = await loadPyodide({
      indexURL: new URL(`/pyodide/v${version}/`, self.location.origin).href,
      packages: ["pandas"],
    });
    py.globals.set("SOURCE", source);
    py.runPython(source);
    return py;
  })();
  python.catch(() => (python = null)); // let the next job try again
  return python;
}

async function ensurePackages(py: PyodideInterface, names: string[]) {
  const missing = names.filter((n) => !(n in py.loadedPackages));
  if (missing.length === 0) return;
  setState({ state: "loading", message: "Getting more statistics tools ready (first time only)" });
  await py.loadPackage(missing, { messageCallback: () => {} });
}

/** Calls a stats.py engine_* function, which returns (JSON, bytes or None). */
function callPython(py: PyodideInterface, fn: string, ...args: unknown[]) {
  const out = py.globals.get(fn)(...args);
  try {
    const [json, bytes] = out.toJs() as [string, Uint8Array | undefined];
    const value = JSON.parse(json) as { error?: string } & Record<string, unknown>;
    if (value.error) throw new Error(value.error);
    return { value, bytes };
  } finally {
    out.destroy();
  }
}

async function handle(job: Job) {
  let py: PyodideInterface;
  try {
    py = await getPython();
  } catch (e) {
    console.error(e);
    const message = e instanceof Error && e.message === BLOCKED ? BLOCKED : COULD_NOT_LOAD;
    setState({ state: "error", message });
    post({ type: "fail", id: job.id, message });
    return;
  }
  try {
    if (job.type === "load") {
      await ensurePackages(py, py.globals.get("packages_for")(null, job.name).toJs());
      setState({ state: "running", message: "Reading the file" });
      const ext = job.name.includes(".") ? job.name.slice(job.name.lastIndexOf(".")) : "";
      const path = `/tmp/data${ext.replace(/[^.\w]/g, "")}`;
      py.FS.writeFile(path, new Uint8Array(job.bytes));
      try {
        const options = JSON.stringify(job.options ?? {});
        const { value } = callPython(py, "engine_load", path, job.name, job.sheet ?? null, options);
        post({ type: "done", id: job.id, value });
      } finally {
        py.FS.unlink(path); // the table is in memory now; don't keep a second copy
      }
    } else if (job.type === "run") {
      await ensurePackages(py, py.globals.get("packages_for")(job.test).toJs());
      setState({ state: "running", message: "Running the test" });
      const { value, bytes } = callPython(py, "engine_run", job.test, JSON.stringify(job.params));
      const xlsx = new Uint8Array(bytes ?? []);
      post({ type: "done", id: job.id, value: { ...value, xlsx } }, [xlsx.buffer]);
    } else if (job.type === "table_xlsx") {
      await ensurePackages(py, ["openpyxl"]);
      const { bytes } = callPython(
        py,
        "engine_table_xlsx",
        JSON.stringify(job.context),
        JSON.stringify(job.table),
      );
      const xlsx = new Uint8Array(bytes ?? []);
      post({ type: "done", id: job.id, value: xlsx }, [xlsx.buffer]);
    } else if (job.type === "rows") {
      const { value } = callPython(py, "engine_rows", job.offset, job.limit);
      post({ type: "done", id: job.id, value });
    } else {
      if (job.type === "prepare")
        await ensurePackages(py, py.globals.get("packages_for")(job.test).toJs());
      post({ type: "done", id: job.id, value: null });
    }
  } catch (e) {
    const message =
      e instanceof Error && !e.message.includes("Traceback")
        ? e.message
        : "Something went wrong. Try again, or reload the page.";
    if (message !== (e as Error)?.message) console.error(e);
    post({ type: "fail", id: job.id, message });
  }
}

self.onmessage = (event: MessageEvent<Job>) => {
  waiting += 1;
  queue = queue.then(async () => {
    await handle(event.data);
    waiting -= 1;
    if (waiting === 0 && python) setState({ state: "ready" });
  });
};
