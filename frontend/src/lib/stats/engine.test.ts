import { describe, expect, it } from "vitest";
import type { EngineState } from "@/lib/stats/contract";
import { createStatsEngine } from "@/lib/stats/engine";
import type { Reply } from "@/lib/stats/worker";

class FakeWorker {
  onmessage: ((e: MessageEvent<Reply>) => void) | null = null;
  onerror: ((e: ErrorEvent) => void) | null = null;
  posted: { data: { id: number; type: string }; transfer: Transferable[] }[] = [];
  terminated = false;
  postMessage(data: { id: number; type: string }, transfer: Transferable[] = []) {
    this.posted.push({ data, transfer });
  }
  terminate() {
    this.terminated = true;
  }
  reply(r: Reply) {
    this.onmessage?.({ data: r } as MessageEvent<Reply>);
  }
}

function setup() {
  const workers: FakeWorker[] = [];
  const engine = createStatsEngine(() => {
    const w = new FakeWorker();
    workers.push(w);
    return w as unknown as Worker;
  });
  return { engine, workers };
}

const file = (size = 8) => ({ name: "data.csv", bytes: new ArrayBuffer(size) });

describe("stats engine", () => {
  it("passes on state messages, starting from idle", () => {
    const { engine, workers } = setup();
    const seen: EngineState[] = [];
    const stop = engine.subscribe((s) => seen.push(s));
    engine.warmUp();
    engine.warmUp();
    expect(workers).toHaveLength(1);
    const loading = {
      state: "loading",
      message: "Getting the statistics tools ready (first time only)",
    } as const;
    workers[0]!.reply({ type: "state", state: loading });
    workers[0]!.reply({ type: "state", state: { state: "ready" } });
    stop();
    workers[0]!.reply({ type: "state", state: { state: "running", message: "Running the test" } });
    expect(seen).toEqual([{ state: "idle" }, loading, { state: "ready" }]);
  });

  it("sends load before run, moves the bytes, and matches replies by id", async () => {
    const { engine, workers } = setup();
    const f = file();
    const loaded = engine.load(f);
    const ran = engine.run({ test: "describe", params: { columns: ["a"] } });
    const [load, run] = workers[0]!.posted;
    expect(load!.data).toMatchObject({ type: "load", name: "data.csv" });
    expect(load!.transfer).toEqual([f.bytes]);
    expect(run!.data).toMatchObject({ type: "run", test: "describe", params: { columns: ["a"] } });
    workers[0]!.reply({ type: "done", id: run!.data.id, value: { summary: "ok" } });
    workers[0]!.reply({ type: "done", id: load!.data.id, value: { rows: 3 } });
    await expect(loaded).resolves.toEqual({ rows: 3 });
    await expect(ran).resolves.toEqual({ summary: "ok" });
  });

  it("sends load options with the file", () => {
    const { engine, workers } = setup();
    void engine.load(file(), { decimal: ",", missing: { a: [999] } });
    void engine.load({ ...file(), sheet: "Data" });
    const [withOptions, plain] = workers[0]!.posted;
    expect(withOptions!.data).toMatchObject({
      type: "load",
      options: { decimal: ",", missing: { a: [999] } },
    });
    expect(plain!.data).toMatchObject({ type: "load", sheet: "Data", options: undefined });
  });

  it("prepares a test's packages through the same queue, ignoring failures", async () => {
    const { engine, workers } = setup();
    engine.prepare("anova_twoway");
    const ran = engine.run({ test: "anova_twoway", params: {} });
    const [prepare, run] = workers[0]!.posted;
    expect(prepare!.data).toMatchObject({ type: "prepare", test: "anova_twoway" });
    expect(run!.data.id).toBeGreaterThan(prepare!.data.id);
    workers[0]!.reply({ type: "fail", id: prepare!.data.id, message: "offline" });
    workers[0]!.reply({ type: "done", id: run!.data.id, value: { summary: "ok" } });
    await expect(ran).resolves.toEqual({ summary: "ok" });
  });

  it("rejects with the worker's plain message", async () => {
    const { engine, workers } = setup();
    const ran = engine.run({ test: "t_independent", params: {} });
    const message = 'The independent t-test needs exactly two groups, but "g" has 3.';
    workers[0]!.reply({ type: "fail", id: workers[0]!.posted[0]!.data.id, message });
    await expect(ran).rejects.toThrow(message);
  });

  it("refuses files over 100 MB without sending them", async () => {
    const { engine, workers } = setup();
    await expect(engine.load(file(100 * 1024 * 1024 + 1))).rejects.toThrow("over 100 MB");
    expect(workers).toHaveLength(0);
  });

  it("recovers from a crashed worker", async () => {
    const { engine, workers } = setup();
    const seen: EngineState[] = [];
    engine.subscribe((s) => seen.push(s));
    const ran = engine.run({ test: "describe", params: {} });
    workers[0]!.onerror?.(new ErrorEvent("error"));
    await expect(ran).rejects.toThrow("stopped working");
    expect(workers[0]!.terminated).toBe(true);
    expect(seen.at(-1)).toEqual({ state: "error", message: expect.stringContaining("stopped") });
    void engine.load(file());
    expect(workers).toHaveLength(2);
  });
});

describe("test catalogue", () => {
  it("has a Python function for every test the screens list, and a unique id and label", async () => {
    const { TESTS } = await import("@/lib/stats/contract");
    const py = (await import("@/lib/stats/stats.py?raw")).default;
    for (const t of TESTS) expect(py, t.id).toContain(`def ${t.id}(`);
    expect(new Set(TESTS.map((t) => t.id)).size).toBe(TESTS.length);
    expect(new Set(TESTS.map((t) => t.label)).size).toBe(TESTS.length);
    expect(TESTS.length).toBeGreaterThanOrEqual(28);
  });
});
