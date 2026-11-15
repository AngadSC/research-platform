import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Flow } from "@/hooks/participants";
import { flowRows, flowSvg, flowTableHtml } from "@/lib/flowExport";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const user = { id: "u1", email: "ada@uni.edu", display_name: "Ada" };
const P = "/api/labs/lab1/projects/p1";
const project = {
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
  my_permissions: ["view_project", "edit_content", "edit_project", "export"],
};
const person = (id: string, code: string) => ({
  id,
  code,
  group: "",
  cohort: "",
  enrolment_status: "enrolled",
  enrolled_on: null,
  completed_on: null,
  notes: "",
  archived_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});
const column = {
  id: "t",
  name: "Transcript",
  key: "transcript",
  category: "transcript",
  required: true,
  applies_to_groups: [],
  order: 0,
  expected_per_participant: 1,
  template_origin: "",
  sensitive: false,
  archived_at: null,
};
const cell = (p: string, status: string, extra: Record<string, unknown> = {}) => ({
  id: `c-${p}`,
  participant: p,
  component: "t",
  status,
  reason: null,
  owner: null,
  decision: null,
  due_date: null,
  collected_on: null,
  note: "",
  files: [],
  tasks: [],
  suggested_status: null,
  verified_at: null,
  changed_since_verified: false,
  updated_at: "2026-01-01T00:00:00Z",
  ...extra,
});
const flow: Flow = {
  screened: { count: 12, small: false },
  enrolled: { count: 10, small: false },
  completed: { count: 8, small: false },
  withdrawn: { count: 2, small: true },
  ineligible: { count: 0, small: false },
  excluded: [{ reason: "Duplicate", count: 1, small: true }],
  analysed: { count: 7, small: false },
  groups: [],
  set: "Figure 2",
  small_cell_limit: 5,
  warning: "Some counts are under 5.",
};

function world(extra: Parameters<typeof mockFetch>[0] = {}) {
  return mockFetch({
    [SESSION]: signedIn,
    "GET /api/labs/": { body: [makeLab(["view_lab"])] },
    "GET /api/labs/lab1/": { body: makeLab(["view_lab"]) },
    "GET /api/labs/lab1/projects/": { body: [project] },
    [`GET ${P}/`]: { body: project },
    [`GET ${P}/documents/`]: { body: [] },
    "GET /api/me/": { body: { id: "u1", email: "ada@uni.edu", display_name: "Ada" } },
    "GET /api/labs/lab1/members/": { body: [{ id: "m1", user, role: "pi" }] },
    [`GET ${P}/participants/`]: { body: [person("a", "P-001"), person("b", "P-002")] },
    [`GET ${P}/participant-components/`]: { body: [column] },
    [`GET ${P}/participant-cells/`]: {
      body: [cell("a", "missing", { reason: "r1" }), cell("b", "not_started")],
    },
    [`GET ${P}/participant-link-health/`]: {
      body: {
        counts: { total: 0, ok: 0, unchecked: 0, problems: 0, changed_since_verified: 0 },
        problems: [],
        changed: [],
      },
    },
    "GET /api/labs/lab1/participant-reasons/": {
      body: [{ id: "r1", label: "Did not attend", kind: "missing", active: true }],
    },
    ...extra,
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("flow export", () => {
  it("builds counts only, flags small numbers and carries the warning", () => {
    const rows = flowRows(flow);
    expect(rows.map((r) => r.label)).toContain("Analysed (Figure 2)");
    expect(rows.find((r) => r.label === "Withdrew")?.small).toBe(true);
    const html = flowTableHtml(flow);
    expect(html).toContain("2 *");
    expect(html).toContain("Fewer than 5");
    const svg = flowSvg(flow);
    expect(svg.startsWith("<svg")).toBe(true);
    expect(svg).toContain("Excluded: Duplicate");
  });

  it("escapes anything that could be markup", () => {
    const f = { ...flow, excluded: [{ reason: "<b>x</b>", count: 6, small: false }] };
    expect(flowTableHtml(f)).not.toContain("<b>x</b>");
    expect(flowSvg(f)).not.toContain("<b>x</b>");
  });
});

describe("tasks from gaps", () => {
  it("selecting cells and choosing Create tasks asks for one task per cell", async () => {
    const calls = world({
      [`POST ${P}/participant-tasks/`]: {
        status: 201,
        body: { created: 2, skipped: 0, tasks: [] },
      },
    });
    renderRoute("/labs/lab1/projects/p1/participants");
    const a = await screen.findByRole("button", { name: /P-001, Transcript/ });
    const b = await screen.findByRole("button", { name: /P-002, Transcript/ });
    const u = userEvent.setup(); // one instance, so the held Shift key carries to the click
    await u.click(a);
    await u.keyboard("{Shift>}");
    await u.click(b);
    await u.keyboard("{/Shift}");
    const bar = await screen.findByRole("region", { name: "Change selected cells" });
    await userEvent.click(within(bar).getByRole("button", { name: "Create tasks" }));
    await waitFor(() => {
      const post = calls.find((c) => c.method === "POST" && c.path.endsWith("participant-tasks/"));
      expect(post?.body).toMatchObject({ mode: "cell" });
      expect((post?.body as { cells: unknown[] }).cells).toHaveLength(2);
    });
  });
});

describe("rules dialog", () => {
  it("shows who counts as the rule is written and locks a set from a saved rule", async () => {
    const calls = world({
      [`GET ${P}/participant-rules/`]: {
        body: [
          {
            id: "r1",
            name: "Paper 3",
            description: "",
            version: 2,
            spec: { requires: ["transcript"], groups: [], exclude_enrolment: [] },
          },
        ],
      },
      [`GET ${P}/analysis-sets/`]: { body: [] },
      [`GET ${P}/participant-flow/`]: { body: flow },
      [`POST ${P}/participant-rules/preview/`]: {
        body: {
          eligible: ["P-001"],
          one_away: [
            { code: "P-002", blocking: [{ column: "Transcript", status: "not_started" }] },
          ],
          not_eligible: 0,
          not_eligible_why: {},
        },
      },
      [`POST ${P}/analysis-sets/`]: {
        status: 201,
        body: {
          id: "s1",
          name: "Paper 3",
          rule: "r1",
          rule_version: 2,
          size: 1,
          locked_at: "2026-01-01T00:00:00Z",
          analysis: null,
          supersedes: null,
        },
      },
    });
    renderRoute("/labs/lab1/projects/p1/participants");
    await userEvent.click(await screen.findByRole("button", { name: "Rules and flow" }));
    expect(await screen.findByText(/version 2/)).toBeInTheDocument();
    expect(await screen.findByText("Analysed (Figure 2)")).toBeInTheDocument();
    expect(screen.getByText(/Some counts are under 5/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "New rule" }));
    await userEvent.click(screen.getByLabelText("Transcript"));
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("1 eligible");
    expect(status).toHaveTextContent("P-002 needs Transcript");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await userEvent.click(screen.getByRole("button", { name: "Lock a set" }));
    await waitFor(() =>
      expect(
        calls.find((c) => c.method === "POST" && c.path.endsWith("analysis-sets/"))?.body,
      ).toEqual({ name: "Paper 3", rule: "r1" }),
    );
  });
});

describe("participant cards", () => {
  it("lists what is waiting on you, or says you are caught up", async () => {
    const base = {
      projects: [
        {
          id: "p1",
          name: "Gut study",
          color: "blue",
          participants: 2,
          percent: 50,
          missing: 1,
          overdue: 0,
          needs_review: 0,
        },
      ],
      by_component: [],
      missing_by_reason: [{ reason: "Did not attend", count: 1 }],
      translation_pending: [],
      recent: [],
    };
    world({
      "GET /api/labs/lab1/participant-overview/": {
        body: {
          ...base,
          waiting_on_me: [
            {
              project: "p1",
              project_name: "Gut study",
              participant: "P-001",
              participant_id: "a",
              component: "Transcript",
              status: "missing",
              due_date: null,
              at: "2026-01-01T00:00:00Z",
            },
          ],
        },
      },
    });
    renderRoute("/labs/lab1/my-work");
    expect(await screen.findByText("P-001, Transcript")).toBeInTheDocument();
  });
});
