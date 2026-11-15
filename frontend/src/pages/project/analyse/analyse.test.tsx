import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DataShape, EngineState, StatsEngine, StatsResult } from "@/lib/stats/contract";
import { upload } from "@/lib/api";
import AnalysePage from "@/pages/project/analyse/AnalysePage";
import { StatsEngineProvider } from "@/pages/project/analyse/engine";
import { mockFetch, SESSION, signedIn } from "@/test/utils";

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  upload: vi.fn(),
}));
vi.mock("@/pages/project/analyse/png", () => ({
  svgToPng: vi.fn(async () => new Blob(["png"])),
}));

const P = "/api/labs/lab1/projects/p1";
const col = (name: string, kind: "numeric" | "categorical" | "text") => ({
  name,
  kind,
  missing: 0,
  distinct: 3,
  sample: [1, 2],
});
const shape: DataShape = {
  fileName: "data.csv",
  sheets: [],
  sheet: null,
  rows: 6,
  columns: [col("score", "numeric"), col("arm", "categorical"), col("note", "text")],
  issues: [],
};
const result: StatsResult = {
  test: "t_independent",
  title: "Score by arm",
  summary: "t(4) = 2.31, p = .026",
  tables: [{ title: "Group means", columns: ["Group", "Mean"], rows: [["A", 1.5]] }],
  charts: [
    {
      kind: "box",
      title: "Score by arm",
      yLabel: "score",
      groups: [{ name: "A", values: [1, 2, 3] }],
    },
  ],
  warnings: ["One row had no score and was left out."],
  n: 5,
  code: "print('hi')",
  xlsx: new Uint8Array([1, 2]),
};

function fakeEngine(over: Partial<StatsEngine> = {}) {
  let listener: (s: EngineState) => void = () => {};
  const e: StatsEngine & { load: ReturnType<typeof vi.fn>; run: ReturnType<typeof vi.fn> } = {
    warmUp: vi.fn(),
    subscribe: (l: (s: EngineState) => void) => {
      listener = l;
      return () => {};
    },
    load: vi.fn(async () => shape),
    run: vi.fn(async () => result),
    ...over,
  } as never;
  return Object.assign(e, { emit: (s: EngineState) => listener(s) });
}

const att = (id: string, name: string, extra: Record<string, unknown> = {}) => ({
  id,
  original_filename: name,
  content_type: "text/csv",
  drive_file_id: "",
  external_url: "",
  contains_participant_data: false,
  ...extra,
});
const project = (perms = ["view_project", "edit_content"]) => ({
  id: "p1",
  name: "Gut study",
  status: "active",
  my_permissions: perms,
});

function setup(
  engine: StatsEngine,
  {
    files = [att("a1", "data.csv")],
    datasets = [] as unknown[],
    query = "",
    perms,
    extra = {},
    slowFolders = false,
  }: {
    files?: unknown[];
    datasets?: unknown[];
    query?: string;
    perms?: string[];
    extra?: Record<string, never>;
    /** The folder list arrives after everything else. */
    slowFolders?: boolean;
  } = {},
) {
  const calls = mockFetch({
    [SESSION]: signedIn,
    [`GET ${P}/attachments/`]: { body: files },
    [`GET ${P}/datasets/`]: { body: datasets },
    [`GET ${P}/folders/`]: { body: [] },
    "GET /api/labs/lab1/attachments/a1/download/?stream=1": { body: "x" },
    "GET /api/labs/lab1/attachments/a2/download/?stream=1": { body: "x" },
    ...extra,
  });
  const quick = globalThis.fetch;
  if (slowFolders)
    vi.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/folders/")) await new Promise((r) => setTimeout(r, 100));
      return quick(input, init);
    });
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <StatsEngineProvider get={() => engine}>
        <MemoryRouter initialEntries={[`/p/analyse${query}`]}>
          <Routes>
            <Route
              path="/p/analyse"
              element={
                <AnalysePage labId="lab1" projectId="p1" project={project(perms) as never} />
              }
            />
          </Routes>
        </MemoryRouter>
      </StatsEngineProvider>
    </QueryClientProvider>,
  );
  return calls;
}

async function loadAndRun(u: ReturnType<typeof userEvent.setup>) {
  await u.selectOptions(await screen.findByLabelText("From this project"), "file:a1");
  await screen.findByText(/6 rows, 3 columns/);
  await u.selectOptions(screen.getByLabelText("Test"), "t_independent");
  await u.selectOptions(screen.getByLabelText("Outcome (numbers)"), "score");
  await u.selectOptions(screen.getByLabelText("Groups"), "arm");
  await u.click(screen.getByRole("button", { name: "Run" }));
}

beforeEach(() => {
  vi.mocked(upload).mockReset();
});
afterEach(() => vi.unstubAllGlobals());

describe("Analyse page", () => {
  it("loads a file, filters pickers by kind, runs and shows the result", async () => {
    const engine = fakeEngine();
    setup(engine);
    const u = userEvent.setup();
    expect(engine.warmUp).toHaveBeenCalled();
    await u.selectOptions(await screen.findByLabelText("From this project"), "file:a1");
    expect(await screen.findByText(/6 rows, 3 columns/)).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "note" })).toBeInTheDocument();
    await u.selectOptions(screen.getByLabelText("Test"), "t_independent");
    const outcome = screen.getByLabelText("Outcome (numbers)");
    expect(
      within(outcome)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["Choose", "score"]);
    const groups = screen.getByLabelText("Groups");
    expect(
      within(groups)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["Choose", "arm", "score", "note"]);
    await u.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findAllByText("Choose a column.")).toHaveLength(2);
    expect(engine.run).not.toHaveBeenCalled();
    await u.selectOptions(outcome, "score");
    await u.selectOptions(groups, "arm");
    await u.click(screen.getByRole("button", { name: "Run" }));
    expect(await screen.findByText("t(4) = 2.31, p = .026")).toBeInTheDocument();
    expect(engine.run).toHaveBeenCalledWith({
      test: "t_independent",
      params: { outcome: "score", group: "arm", variant: "welch" },
    });
    expect(screen.getByRole("table", { name: "Group means" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Score by arm" })).toBeInTheDocument();
    expect(screen.getByText("One row had no score and was left out.")).toBeInTheDocument();
  });

  it("shows the engine's message when a run fails", async () => {
    const engine = fakeEngine({
      run: vi.fn().mockRejectedValue(new Error("Pick exactly two groups.")),
    });
    setup(engine);
    await loadAndRun(userEvent.setup());
    expect(await screen.findByText("Pick exactly two groups.")).toBeInTheDocument();
  });

  it("shows the engine's progress message", async () => {
    const engine = fakeEngine();
    setup(engine);
    await screen.findByLabelText("From this project");
    (await import("@testing-library/react")).act(() =>
      engine.emit({ state: "loading", message: "Getting the statistics tools ready" }),
    );
    expect(screen.getByText("Getting the statistics tools ready")).toBeInTheDocument();
  });

  it("disables files that live in Google Drive and says what to do", async () => {
    setup(fakeEngine(), {
      files: [
        att("a1", "data.csv"),
        att("g1", "Trial sheet", {
          drive_file_id: "d",
          content_type: "application/vnd.google-apps.spreadsheet",
        }),
      ],
    });
    expect(await screen.findByRole("option", { name: /Trial sheet/ })).toBeDisabled();
    expect(
      screen.getByText(/Download it from Google Drive, then choose From this computer/),
    ).toBeInTheDocument();
  });

  it("opens the dataset named in the address", async () => {
    const engine = fakeEngine();
    setup(engine, {
      query: "?dataset=d1",
      datasets: [
        { id: "d1", name: "Stool", data_file: { id: "a1" }, contains_participant_data: false },
      ],
    });
    await waitFor(() => expect(engine.load).toHaveBeenCalled());
    expect(engine.load.mock.calls[0]![0].name).toBe("data.csv");
  });

  it("opens the file named in the address", async () => {
    const engine = fakeEngine();
    setup(engine, { query: "?file=a1" });
    await waitFor(() => expect(engine.load).toHaveBeenCalled());
  });

  it("shows what is odd about the file and reloads it with a fix", async () => {
    const fix = { header: 0, skip: 0, missing: { score: [999] } };
    const engine = fakeEngine();
    engine.load
      .mockResolvedValueOnce({
        ...shape,
        issues: [
          { id: "m", message: '"score" has 999 in 1 row.', action: "Treat 999 as missing", fix },
        ],
      })
      .mockResolvedValueOnce({
        ...shape,
        issues: [
          { id: "m", message: '999 in "score" is treated as missing.', fix: {}, applied: true },
        ],
      });
    setup(engine);
    const u = userEvent.setup();
    await u.selectOptions(await screen.findByLabelText("From this project"), "file:a1");
    await u.click(await screen.findByRole("button", { name: "Treat 999 as missing" }));
    expect(engine.load.mock.calls[1]![0]).toMatchObject({ name: "data.csv", sheet: undefined });
    expect(engine.load.mock.calls[1]![1]).toEqual(fix);
    await u.click(await screen.findByRole("button", { name: "Undo" }));
    expect(engine.load.mock.calls[2]![1]).toEqual({});
  });

  it("saves the files, then the analysis, then the result, then the Google copy", async () => {
    const order: string[] = [];
    vi.mocked(upload).mockImplementation(async (_p, form) => {
      const f = (form as FormData).get("file") as File;
      order.push(
        `upload ${f.name} ${(form as FormData).get("contains_participant_data") ?? "no-mark"}`,
      );
      return { id: `id-${f.name}` } as never;
    });
    const calls = setup(fakeEngine(), {
      datasets: [
        { id: "d1", name: "Stool", data_file: { id: "a1" }, contains_participant_data: false },
      ],
      query: "?dataset=d1",
      extra: {
        [`POST ${P}/analyses/`]: { status: 201, body: { id: "an1" } },
        [`POST ${P}/results/`]: { status: 201, body: { id: "r1" } },
        "POST /api/labs/lab1/attachments/id-score-by-arm.xlsx/edit-in-google/": {
          status: 200,
          body: {
            id: "g9",
            drive_file_id: "gd9",
            content_type: "application/vnd.google-apps.spreadsheet",
            original_filename: "x",
          },
        },
      } as never,
    });
    const u = userEvent.setup();
    await screen.findByText(/6 rows, 3 columns/);
    await u.selectOptions(screen.getByLabelText("Test"), "t_independent");
    await u.selectOptions(screen.getByLabelText("Outcome (numbers)"), "score");
    await u.selectOptions(screen.getByLabelText("Groups"), "arm");
    await u.click(screen.getByRole("button", { name: "Run" }));
    await u.click(await screen.findByRole("button", { name: "Save to project" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Title")).toHaveValue("Score by arm");
    await u.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("link", { name: "Open in Google Sheets" })).toBeInTheDocument();
    expect(order).toEqual([
      "upload score-by-arm.xlsx no-mark",
      "upload score-by-arm.py no-mark",
      "upload score-by-arm-chart-1.png no-mark",
    ]);
    const posts = calls.filter((c) => c.method === "POST").map((c) => c.path);
    expect(posts.slice(-3)).toEqual([
      `${P}/analyses/`,
      `${P}/results/`,
      "/api/labs/lab1/attachments/id-score-by-arm.xlsx/edit-in-google/",
    ]);
    const analysis = calls.find((c) => c.path === `${P}/analyses/` && c.method === "POST")!
      .body as Record<string, unknown>;
    expect(analysis).toMatchObject({
      title: "Score by arm",
      code_attachment: "id-score-by-arm.py",
      datasets: ["d1"],
      description:
        "t(4) = 2.31, p = .026\n\nInput file: data.csv\n\nRun in the browser with labbenchos statistics.",
    });
    expect(typeof analysis.ran_at).toBe("string");
    expect(calls.find((c) => c.path === `${P}/results/` && c.method === "POST")!.body).toEqual({
      title: "Score by arm",
      summary: "t(4) = 2.31, p = .026",
      analysis: "an1",
      attachments: ["id-score-by-arm.xlsx", "id-score-by-arm-chart-1.png"],
    });
  });

  it("saves marked files only, with no analysis or result, when the data identifies participants", async () => {
    vi.mocked(upload).mockImplementation(async (_p, form) => {
      const f = (form as FormData).get("file") as File;
      expect((form as FormData).get("contains_participant_data")).toBe("true");
      return { id: `id-${f.name}` } as never;
    });
    const calls = setup(fakeEngine(), {
      files: [att("a1", "data.csv", { contains_participant_data: true })],
    });
    const u = userEvent.setup();
    await loadAndRun(u);
    await u.click(await screen.findByRole("button", { name: "Save to project" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(/so none is made for data that identifies/),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole("checkbox", { name: /Google Sheet copy/ })).not.toBeChecked();
    const save = within(dialog).getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
    await u.click(within(dialog).getByRole("checkbox", { name: /my ethics approval allows/ }));
    await u.click(save);
    expect(await screen.findByRole("link", { name: "Open the files" })).toHaveAttribute(
      "href",
      "/labs/lab1/projects/p1/documents",
    );
    expect(upload).toHaveBeenCalledTimes(3);
    // analysis and result records can't carry the mark and AI tools read them
    expect(calls.filter((c) => c.method === "POST")).toEqual([]);
  });

  it("counts a file in a marked folder as marked, waiting for the folder list", async () => {
    const calls = setup(fakeEngine(), {
      files: [att("a1", "data.csv", { folder: "f1" })],
      query: "?file=a1",
      slowFolders: true,
      extra: {
        [`GET ${P}/folders/`]: { body: [{ id: "f1", contains_participant_data: true }] },
      } as never,
    });
    const u = userEvent.setup();
    await screen.findByText(/6 rows, 3 columns/);
    expect(calls.some((c) => c.path.endsWith("/folders/"))).toBe(true);
    await u.selectOptions(screen.getByLabelText("Test"), "t_independent");
    await u.selectOptions(screen.getByLabelText("Outcome (numbers)"), "score");
    await u.selectOptions(screen.getByLabelText("Groups"), "arm");
    await u.click(screen.getByRole("button", { name: "Run" }));
    await u.click(await screen.findByRole("button", { name: "Save to project" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/The data file identifies participants/)).toBeInTheDocument();
  });

  it("asks the participant question when the folder list could not be read", async () => {
    setup(fakeEngine(), {
      files: [att("a1", "data.csv", { folder: "f1" })],
      extra: { [`GET ${P}/folders/`]: { status: 500, body: {} } } as never,
    });
    const u = userEvent.setup();
    await loadAndRun(u);
    await u.click(await screen.findByRole("button", { name: "Save to project" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByRole("radio", { name: /identifies participants/ }),
    ).toBeInTheDocument();
  });

  it("keeps grant files out of the picker and out of links", async () => {
    const engine = fakeEngine();
    setup(engine, {
      files: [att("a1", "data.csv"), att("a2", "budget.xlsx", { pi_only: true })],
      query: "?file=a2",
    });
    expect(await screen.findByRole("option", { name: /budget\.xlsx/ })).toBeDisabled();
    expect(screen.getByText("Grant files can't be analysed here.")).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 50));
    expect(engine.load).not.toHaveBeenCalled();
  });

  it("asks the participant question for a file from this computer", async () => {
    setup(fakeEngine(), { files: [] });
    const u = userEvent.setup();
    await u.upload(
      await screen.findByLabelText("From this computer"),
      new File(["a,b"], "mine.csv"),
    );
    await screen.findByText(/6 rows/);
    await u.selectOptions(screen.getByLabelText("Test"), "describe");
    await u.click(screen.getByRole("checkbox", { name: "score" }));
    await u.click(screen.getByRole("button", { name: "Run" }));
    await u.click(await screen.findByRole("button", { name: "Save to project" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByRole("radio", { name: /identifies participants/ }),
    ).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("says exactly what was saved when a step fails", async () => {
    vi.mocked(upload)
      .mockResolvedValueOnce({ id: "x1" } as never)
      .mockRejectedValueOnce(new Error("The server is busy."));
    setup(fakeEngine());
    const u = userEvent.setup();
    await loadAndRun(u);
    await u.click(await screen.findByRole("button", { name: "Save to project" }));
    await u.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Save" }));
    expect(
      await screen.findByText(
        "Saved so far: score-by-arm.xlsx. Could not upload score-by-arm.py: The server is busy.",
      ),
    ).toBeInTheDocument();
  });

  it("hides Save to project without edit rights", async () => {
    setup(fakeEngine(), { perms: ["view_project"] });
    await loadAndRun(userEvent.setup());
    await screen.findByText("t(4) = 2.31, p = .026");
    expect(screen.queryByRole("button", { name: "Save to project" })).toBeNull();
  });
});
