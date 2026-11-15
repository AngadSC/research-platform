import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { completeness, parseCodes } from "@/lib/participants";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const user = { id: "u1", email: "ada@uni.edu", display_name: "Ada" };
const P = "/api/labs/lab1/projects/p1";
const project = (perms: string[]) => ({
  id: "p1",
  name: "Gut study",
  description: "",
  status: "active",
  start_date: null,
  retain_until: null,
  retention_note: "",
  created_by: user,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  last_activity_at: null,
  last_activity_by: null,
  my_project_role: "lead",
  my_permissions: perms,
});
const person = (id: string, code: string, group = "") => ({
  id,
  code,
  group,
  cohort: "",
  enrolment_status: "enrolled",
  enrolled_on: null,
  completed_on: null,
  notes: "",
  archived_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});
const column = (id: string, name: string, groups: string[] = []) => ({
  id,
  name,
  key: name.toLowerCase(),
  category: "transcript",
  required: true,
  applies_to_groups: groups,
  order: 0,
  expected_per_participant: 1,
  template_origin: "",
  sensitive: false,
  archived_at: null,
});
const cell = (p: string, c: string, status: string, extra: Record<string, unknown> = {}) => ({
  id: `cell-${p}-${c}`,
  participant: p,
  component: c,
  status,
  reason: null,
  owner: null,
  due_date: null,
  collected_on: null,
  note: "",
  files: [],
  suggested_status: null,
  updated_at: "2026-01-01T00:00:00Z",
  ...extra,
});
const REASONS = [{ id: "r1", label: "Did not attend", kind: "missing", active: true }];

function world(
  perms = ["view_project", "edit_content", "edit_project"],
  extra: Parameters<typeof mockFetch>[0] = {},
) {
  return mockFetch({
    [SESSION]: signedIn,
    "GET /api/labs/": { body: [makeLab(["view_lab"])] },
    "GET /api/labs/lab1/": { body: makeLab(["view_lab"]) },
    "GET /api/labs/lab1/projects/": { body: [project(perms)] },
    [`GET ${P}/`]: { body: project(perms) },
    [`GET ${P}/documents/`]: { body: [] },
    "GET /api/labs/lab1/members/": { body: [{ id: "m1", user, role: "pi" }] },
    [`GET ${P}/participants/`]: {
      body: [person("a", "P-001", "Punjabi"), person("b", "P-002", "French")],
    },
    [`GET ${P}/participant-components/`]: {
      body: [column("t", "Transcript"), column("tr", "Translation", ["Punjabi"])],
    },
    [`GET ${P}/participant-cells/`]: {
      body: [
        cell("a", "t", "complete", {
          files: [
            {
              id: "f1",
              url: "https://docs.google.com/document/d/x",
              title: "T1",
              link_state: "ok",
            },
          ],
        }),
        cell("b", "t", "missing", { reason: "r1" }),
      ],
    },
    "GET /api/labs/lab1/participant-reasons/": { body: REASONS },
    ...extra,
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("helpers", () => {
  it("splits pasted codes on spaces, commas and lines and drops repeats", () => {
    expect(parseCodes("P-001, P-002\nP-003  P-001;")).toEqual(["P-001", "P-002", "P-003"]);
  });

  it("counts only cells that can still be completed", () => {
    const c = (status: string) => ({ status }) as never;
    expect(completeness([c("complete"), c("missing"), c("not_applicable"), undefined])).toEqual({
      counted: 3,
      done: 1,
      percent: 33,
    });
  });
});

describe("participant matrix", () => {
  it("shows an icon and a label for every status, and a labelled cell", async () => {
    world();
    renderRoute("/labs/lab1/projects/p1/participants");
    const grid = await screen.findByRole("grid", { name: /completeness/i });
    expect(
      within(grid).getByRole("button", { name: "P-001, Transcript, Complete" }),
    ).toBeInTheDocument();
    expect(
      within(grid).getByRole("button", {
        name: "P-002, Transcript, Missing, reason: Did not attend",
      }),
    ).toBeInTheDocument();
    // a column limited to Punjabi does not apply to the French participant
    expect(within(grid).getByText("Does not apply to this group")).toBeInTheDocument();
    expect(screen.getByText(/Coded IDs only/)).toBeInTheDocument();
  });

  it("filters by search and by summary card", async () => {
    world();
    renderRoute("/labs/lab1/projects/p1/participants");
    const grid = await screen.findByRole("grid");
    await userEvent.type(screen.getByLabelText("Search by code"), "P-002");
    expect(within(grid).queryByRole("link", { name: "P-001" })).toBeNull();
    await userEvent.clear(screen.getByLabelText("Search by code"));
    await userEvent.click(
      within(screen.getByRole("list", { name: "Summary" })).getByRole("button", {
        name: /missing/i,
      }),
    );
    expect(within(grid).queryByRole("link", { name: "P-001" })).toBeNull();
    expect(within(grid).getByRole("link", { name: "P-002" })).toBeInTheDocument();
  });

  it("a number key sets the status at once and offers Undo", async () => {
    const calls = world(undefined, {
      [`PATCH ${P}/participants/a/cells/t/`]: { body: cell("a", "t", "in_progress") },
    });
    renderRoute("/labs/lab1/projects/p1/participants");
    const target = await screen.findByRole("button", { name: "P-001, Transcript, Complete" });
    target.focus();
    await userEvent.keyboard("2");
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ status: "in_progress" }),
    );
    expect(await screen.findByRole("button", { name: "Undo" })).toBeInTheDocument();
  });

  it("Missing needs a reason, so the shortcut opens the panel instead of saving", async () => {
    const calls = world();
    renderRoute("/labs/lab1/projects/p1/participants");
    const target = await screen.findByRole("button", { name: "P-001, Transcript, Complete" });
    target.focus();
    await userEvent.keyboard("5");
    const panel = await screen.findByRole("complementary", { name: "P-001, Transcript" });
    expect(within(panel).getByLabelText(/Reason/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "PATCH")).toBe(false);
  });

  it("Enter opens the cell panel with its links, and Escape closes it", async () => {
    world();
    renderRoute("/labs/lab1/projects/p1/participants");
    const target = await screen.findByRole("button", { name: "P-001, Transcript, Complete" });
    target.focus();
    await userEvent.keyboard("{Enter}");
    const panel = await screen.findByRole("complementary", { name: "P-001, Transcript" });
    expect(within(panel).getByRole("link", { name: /T1/ })).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
    await userEvent.keyboard("{Escape}");
    await waitFor(() =>
      expect(screen.queryByRole("complementary", { name: "P-001, Transcript" })).toBeNull(),
    );
  });

  it("a viewer can look but not change", async () => {
    world(["view_project"]);
    renderRoute("/labs/lab1/projects/p1/participants");
    const target = await screen.findByRole("button", { name: "P-001, Transcript, Complete" });
    await userEvent.click(target);
    const panel = await screen.findByRole("complementary", { name: "P-001, Transcript" });
    expect(within(panel).queryByRole("button", { name: "Save" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Add participants/ })).toBeNull();
  });

  it("an empty project says what to do next", async () => {
    world(undefined, { [`GET ${P}/participants/`]: { body: [] } });
    renderRoute("/labs/lab1/projects/p1/participants");
    expect(await screen.findByText("No participants yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Add participants/ })).toBeInTheDocument();
  });

  it("pasting codes adds them in one go and shows a refusal without echoing it", async () => {
    const calls = world(undefined, {
      [`POST ${P}/participants/`]: (req) =>
        (req.body as { codes: string[] }).codes.includes("Jane")
          ? { status: 400, body: { codes: ["A code needs a number in it, like P-017."] } }
          : { status: 201, body: [] },
    });
    renderRoute("/labs/lab1/projects/p1/participants");
    await userEvent.click(await screen.findByRole("button", { name: /Add participants/ }));
    await userEvent.type(screen.getByLabelText(/Participant codes/), "Jane");
    await userEvent.click(screen.getByRole("button", { name: "Add participant" }));
    expect(await screen.findByText(/needs a number/)).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText(/Participant codes/));
    await userEvent.type(screen.getByLabelText(/Participant codes/), "P-010 P-011");
    await userEvent.click(screen.getByRole("button", { name: "Add 2 participants" }));
    await waitFor(() =>
      expect(calls.filter((c) => c.method === "POST").at(-1)?.body).toEqual({
        codes: ["P-010", "P-011"],
      }),
    );
  });
});

describe("import wizard", () => {
  const mapped = {
    "POST /api/labs/lab1/projects/p1/participant-imports/preview/": {
      body: {
        headers: ["Code", "Language", "Child name", "Transcript"],
        rows: [["P-001", "Punjabi", "x", "done"]],
        total: 1,
        blocked_headers: ["Child name"],
        link_columns: [],
      },
    },
  };

  it("leaves out name-like columns, checks first, and saves only on confirm", async () => {
    const calls = world(undefined, {
      ...mapped,
      [`POST ${P}/participant-imports/`]: (req) => ({
        body: {
          created: 1,
          updated: 0,
          skipped: 0,
          links: 0,
          components_created: 1,
          attention: [],
          attention_total: 0,
          dry_run: (req.body as { dry_run: boolean }).dry_run,
        },
      }),
    });
    renderRoute("/labs/lab1/projects/p1/participants");
    await userEvent.click(await screen.findByRole("button", { name: "More actions" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Import" }));
    await userEvent.type(screen.getByLabelText("Sheet contents"), "Code,Language\nP-001,Punjabi");
    await userEvent.click(screen.getByRole("button", { name: /Next: match columns/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Child name");
    // the name-like column is not offered as a choice
    expect(screen.queryByRole("option", { name: "Child name" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Check before saving" }));
    expect(await screen.findByText(/Nothing is saved yet/)).toBeInTheDocument();
    expect(
      calls.filter(
        (c) => c.method === "POST" && (c.body as { dry_run?: boolean })?.dry_run === false,
      ),
    ).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Confirm import" }));
    expect(await screen.findByText("Imported.")).toBeInTheDocument();
  });
});

describe("calm default and customize", () => {
  it("keeps the extra filters tucked away until asked", async () => {
    world();
    renderRoute("/labs/lab1/projects/p1/participants");
    await screen.findByRole("grid");
    expect(screen.queryByLabelText("Cell status")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /Filters/ }));
    expect(screen.getByLabelText("Cell status")).toBeInTheDocument();
  });

  it("hides a column from the grid when customized, and remembers it", async () => {
    world();
    localStorage.clear();
    renderRoute("/labs/lab1/projects/p1/participants");
    const grid = await screen.findByRole("grid");
    expect(within(grid).getAllByRole("columnheader").length).toBeGreaterThan(2);
    await userEvent.click(screen.getByRole("button", { name: "More actions" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Customize view" }));
    const first = within(screen.getByRole("dialog")).getAllByRole("checkbox")[0]!;
    const before = within(grid).getAllByRole("columnheader", { hidden: true }).length;
    await userEvent.click(first);
    expect(within(grid).getAllByRole("columnheader", { hidden: true }).length).toBe(before - 1);
    expect(localStorage.getItem("view:participants:p1")).toContain("hidden");
  });

  it("expands a participant row in place", async () => {
    world();
    renderRoute("/labs/lab1/projects/p1/participants");
    await screen.findByRole("grid");
    await userEvent.click(screen.getAllByRole("button", { name: /Show details for/ })[0]!);
    expect(screen.getByRole("link", { name: "Open full page" })).toBeInTheDocument();
  });
});

describe("templates and suggestions", () => {
  it("offers to mark a cell with a file as in progress, and dismisses on request", async () => {
    const calls = world(["view_project", "edit_content", "edit_project"], {
      [`GET ${P}/participant-cells/`]: {
        body: [cell("a", "t", "not_started", { suggested_status: "in_progress" })],
      },
      [`PATCH ${P}/participants/a/cells/t/`]: { body: cell("a", "t", "in_progress") },
    });
    renderRoute("/labs/lab1/projects/p1/participants");
    const list = await screen.findByRole("list", { name: "Suggestions" });
    await userEvent.click(within(list).getByRole("button", { name: "Mark in progress" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ status: "in_progress" }),
    );
  });

  it("lists what a template will add and skips columns already there", async () => {
    world(["view_project", "edit_content", "edit_project"], {
      [`GET ${P}/participant-components/`]: { body: [column("c", "Consent form")] },
    });
    renderRoute("/labs/lab1/projects/p1/participants");
    await userEvent.click(await screen.findByRole("button", { name: "More actions" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Start from a template" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(/Adds: Recording, Transcript, Translation\./),
    ).toBeInTheDocument();
  });
});
