import type {
  DataShape,
  EngineState,
  LoadOptions,
  StatsEngine,
  StatsFile,
  StatsRequest,
  StatsResult,
  TestId,
} from "@/lib/stats/contract";
import type { Job, Reply } from "@/lib/stats/worker";

export const MAX_FILE_BYTES = 100 * 1024 * 1024;

const CRASHED = "The statistics tools stopped working. Try again.";

type WithoutId<T> = T extends unknown ? Omit<T, "id"> : never;

/** An engine talking to a worker made by `makeWorker` (tests pass a fake one). */
export function createStatsEngine(
  makeWorker: () => Worker = () =>
    new Worker(new URL("./worker.ts", import.meta.url), { type: "module" }),
): StatsEngine {
  let worker: Worker | null = null;
  let state: EngineState = { state: "idle" };
  let nextId = 1;
  const listeners = new Set<(s: EngineState) => void>();
  const pending = new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();

  function setState(next: EngineState) {
    state = next;
    for (const listener of listeners) listener(state);
  }

  function start(): Worker {
    if (worker) return worker;
    const w = makeWorker();
    w.onmessage = (event: MessageEvent<Reply>) => {
      const reply = event.data;
      if (reply.type === "state") return setState(reply.state);
      const job = pending.get(reply.id);
      pending.delete(reply.id);
      if (reply.type === "done") job?.resolve(reply.value);
      else job?.reject(new Error(reply.message));
    };
    w.onerror = (event) => {
      event.preventDefault?.();
      w.terminate();
      worker = null; // the next call starts a fresh worker
      for (const job of pending.values()) job.reject(new Error(CRASHED));
      pending.clear();
      setState({ state: "error", message: CRASHED });
    };
    worker = w;
    return w;
  }

  function send<T>(job: WithoutId<Job>, transfer: Transferable[] = []): Promise<T> {
    const id = nextId++;
    const w = start();
    return new Promise<T>((resolve, reject) => {
      pending.set(id, { resolve: resolve as (v: unknown) => void, reject });
      w.postMessage({ ...job, id }, transfer);
    });
  }

  return {
    warmUp() {
      // Failures show up as the error state; the next call tries again.
      if (state.state === "idle" || state.state === "error")
        send({ type: "warmup" }).catch(() => {});
    },
    subscribe(listener) {
      listeners.add(listener);
      listener(state);
      return () => {
        listeners.delete(listener);
      };
    },
    load(file: StatsFile, options?: LoadOptions) {
      if (file.bytes.byteLength > MAX_FILE_BYTES) {
        return Promise.reject(
          new Error("This file is over 100 MB, too big to analyse in the browser."),
        );
      }
      // The bytes move to the worker without a copy, so file.bytes is empty afterwards.
      return send<DataShape>(
        { type: "load", name: file.name, bytes: file.bytes, sheet: file.sheet, options },
        [file.bytes],
      );
    },
    prepare(test: TestId) {
      // Queued like any job, so it never delays a run that was asked for first.
      send({ type: "prepare", test }).catch(() => {});
    },
    run(req: StatsRequest) {
      return send<StatsResult>({ type: "run", test: req.test, params: req.params });
    },
  };
}

let engine: StatsEngine | null = null;

/** The one statistics engine for the page (a web worker running Pyodide), made on first use. */
export function getStatsEngine(): StatsEngine {
  return (engine ??= createStatsEngine());
}
