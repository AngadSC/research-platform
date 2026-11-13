import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { localDateISO } from "@/lib/format";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const ago = (n: number) => localDateISO(new Date(Date.now() - n * 86_400_000));
const PI = ["view_lab", "manage_lab"];
const list = <T,>(items: T[], total = items.length) => ({ total, items });
const project = (over: Record<string, unknown> = {}) => ({
  id: "p1",
  name: "Alpha",
  status: "active",
  leads: [{ id: "u1", name: "Ada" }],
  open_tasks: 4,
  overdue_tasks: 0,
  in_progress_tasks: 1,
  next_deadline: null,
  last_activity_at: "2026-11-01T10:00:00Z",
  last_activity_by: { id: "u1", name: "Ada" },
  funding_end_date: null,
  funding_status: null,
  health: "green",
  health_reasons: [],
  ...over,
});
const dash = (over: Record<string, unknown> = {}) => ({
  generated_at: "2026-11-05T00:00:00Z",
  summary: {
    active_projects: 2,
    open_tasks: 9,
    overdue_tasks: 3,
    deadlines_soon: 0,
    ethics_attention: 1,
    funding_ending: 0,
    stalled_projects: 0,
    unassigned_tasks: 0,
    integration_problems: 0,
    projects_without_dmp: 0,
  },
  projects: [
    project(),
    project({
      id: "p2",
      name: "Beta",
      overdue_tasks: 3,
      health: "red",
      health_reasons: ["3 overdue tasks"],
    }),
  ],
  attention: {
    overdue_tasks: list(
      [
        {
          id: "t1",
          title: "Order reagents",
          due_date: "2026-11-01",
          days_overdue: 4,
          project_id: "p2",
          project_name: "Beta",
          assignee: null,
        },
      ],
      3,
    ),
    ethics: list([
      {
        id: "e1",
        title: "Pilot REB",
        approval_number: "REB-1",
        expiry_date: ago(4),
        days_left: -4,
        expired: true,
      },
    ]),
    funding: list([]),
    deadlines: list([]),
    stalled: list([]),
    unassigned: list([]),
    integrations: list([]),
    dmp: list([]),
  },
  people: [
    {
      user_id: "u1",
      name: "Ada",
      role: "pi",
      open_tasks: 2,
      overdue_tasks: 0,
      done_last_30_days: 5,
      last_active_at: "2026-11-04T10:00:00Z",
    },
  ],
  ...over,
});
const kinds = (over: Record<string, number> = {}) => ({
  documents: 0,
  files: 0,
  tasks: 0,
  task_updates: 0,
  chat: 0,
  records: 0,
  ...over,
});
const contributions = (over: Record<string, unknown> = {}) => ({
  start: "2025-11-09",
  end: "2026-11-09",
  user_id: null,
  total: 5,
  by_kind: kinds({ tasks: 3, documents: 2 }),
  days: [
    { date: "2026-11-02", count: 3, by_kind: kinds({ tasks: 3 }) },
    { date: "2026-11-09", count: 2, by_kind: kinds({ documents: 2 }) },
  ],
  ...over,
});
const base = (body: unknown, perms = PI) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(perms)] },
  "GET /api/labs/lab1/": { body: makeLab(perms) },
  "GET /api/labs/lab1/projects/": { body: [] },
  "GET /api/labs/lab1/notifications/": { body: [] },
  "GET /api/labs/lab1/dashboard/": { body },
  "GET /api/labs/lab1/training/expiring/": { status: 404, body: { detail: "Not found." } },
  "GET /api/labs/lab1/contributions/": { body: contributions() },
  "GET /api/labs/lab1/my-tasks/": { body: [] },
});

afterEach(() => vi.unstubAllGlobals());

describe("Dashboard", () => {
  it("is Home for a PI, listing only the problems, then the table and people", async () => {
    mockFetch(base(dash()));
    renderRoute("/labs/lab1");
    const overdue = await screen.findByRole("region", { name: /Overdue tasks/ });
    expect(screen.getByRole("heading", { name: "Home" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Summary" })).toBeNull();
    expect(screen.queryByText(/All clear/)).toBeNull();
    expect(within(overdue).getByRole("link", { name: "Order reagents" })).toHaveAttribute(
      "href",
      "/labs/lab1/projects/p2/tasks?task=t1",
    );
    expect(within(overdue).getByText(/Unassigned · 4 days overdue/)).toBeInTheDocument();
    expect(screen.getByText("Showing 1 of 3.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Pilot REB/ })).toHaveAttribute(
      "href",
      "/labs/lab1/ethics/e1",
    );
    expect(screen.getByText("Expired 4 days ago")).toBeInTheDocument();
    expect(screen.getByText("At risk")).toBeInTheDocument();
    expect(screen.getByText("Done in 30 days")).toBeInTheDocument();
    // kinds with nothing wrong are not listed, and training stays hidden without its endpoint
    expect(screen.queryByRole("region", { name: /Deadlines/ })).toBeNull();
    expect(screen.queryByText("Training expiring")).not.toBeInTheDocument();
  });

  it("shows one All clear line when nothing is wrong", async () => {
    const clear = dash({
      attention: {
        overdue_tasks: list([]),
        ethics: list([]),
        funding: list([]),
        deadlines: list([]),
        stalled: list([]),
        unassigned: list([]),
        integrations: list([]),
      },
    });
    mockFetch(base(clear));
    renderRoute("/labs/lab1/dashboard");
    expect(await screen.findByRole("status")).toHaveTextContent("All clear");
    expect(screen.getAllByText(/All clear/)).toHaveLength(1);
    expect(screen.queryByRole("heading", { name: "Needs attention" })).toBeNull();
  });

  it("sorts the project table", async () => {
    mockFetch(base(dash()));
    renderRoute("/labs/lab1/dashboard");
    await screen.findByRole("region", { name: /Overdue tasks/ });
    const names = () =>
      screen
        .getAllByRole("link", { name: /^(Alpha|Beta)$/ })
        .filter((a) => a.getAttribute("href")?.includes("/projects/p"))
        .map((a) => a.textContent);
    await waitFor(() => expect(names()).toEqual(["Beta", "Alpha"])); // worst health first
    await userEvent.click(screen.getByRole("button", { name: "Project" }));
    expect(names()).toEqual(["Alpha", "Beta"]);
    await userEvent.click(screen.getByRole("button", { name: "Project" }));
    expect(names()).toEqual(["Beta", "Alpha"]);
  });

  it("shows the training card when the endpoint answers", async () => {
    mockFetch({
      ...base(dash()),
      "GET /api/labs/lab1/training/expiring/": {
        body: {
          days: 60,
          count: 1,
          expired_count: 0,
          items: [
            {
              user: { id: "u2", email: "bo@uni.edu", display_name: "Bo" },
              requirement: { id: "r1", name: "Biosafety" },
              status: "expiring",
              expires_on: "2026-12-01",
              days_left: 26,
            },
          ],
        },
      },
    });
    renderRoute("/labs/lab1/dashboard");
    expect(await screen.findByRole("link", { name: "Biosafety · Bo" })).toHaveAttribute(
      "href",
      "/labs/lab1/training",
    );
  });

  it("offers to create a project in a lab with none", async () => {
    mockFetch(base(dash({ projects: [] })));
    renderRoute("/labs/lab1/dashboard");
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New project" })).toHaveAttribute(
      "href",
      "/labs/lab1/projects?new=project",
    );
  });

  it("shows a loading skeleton first", async () => {
    mockFetch(base(dash()));
    renderRoute("/labs/lab1/dashboard");
    expect(await screen.findByLabelText("Loading dashboard")).toBeInTheDocument();
    await screen.findByRole("region", { name: /Overdue tasks/ });
  });

  it("shows the lab's activity graph and switches to one person", async () => {
    const calls = mockFetch({
      ...base(dash()),
      "GET /api/labs/lab1/contributions/?user=u1": {
        body: contributions({
          user_id: "u1",
          total: 1,
          by_kind: kinds({ chat: 1 }),
          days: [{ date: "2026-11-05", count: 1, by_kind: kinds({ chat: 1 }) }],
        }),
      },
    });
    renderRoute("/labs/lab1/dashboard");
    const graph = await screen.findByRole("img", { name: /The lab: 5 contributions/ });
    expect(graph).toHaveAccessibleName(/2 documents edited, 3 tasks created/);
    expect(graph.querySelectorAll("[data-date]")).toHaveLength(53 * 7);
    expect(graph.querySelector('[data-date="2026-11-02"]')).toHaveAttribute("data-level", "4");
    expect(graph.querySelector('[data-date="2026-11-09"]')).toHaveAttribute(
      "title",
      expect.stringMatching(/^2 contributions on /),
    );
    expect(graph.querySelector('[data-date="2026-11-10"]')).not.toHaveAttribute("title"); // future
    expect(screen.getByText("In total: 2 documents edited, 3 tasks created.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("combobox", { name: "Person" }));
    await userEvent.click(await screen.findByRole("option", { name: "Ada" }));
    expect(await screen.findByText("Ada: 1 contribution in the last year")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/labs/lab1/contributions/?user=u1")).toBe(true);
  });

  it("tells a viewer they cannot be given tasks, instead of promising some", async () => {
    mockFetch({
      ...base(dash(), ["view_lab"]),
      "GET /api/labs/lab1/": { body: makeLab(["view_lab"], "viewer") },
    });
    renderRoute("/labs/lab1");
    expect(await screen.findByText(/Viewers can't be given tasks/)).toBeInTheDocument();
    expect(screen.queryByText(/will show up here/)).toBeNull();
  });

  it("shows a member their own tasks on Home and never asks for the lab's dashboard", async () => {
    const calls = mockFetch({
      ...base(dash(), ["view_lab", "create_project"]),
      "GET /api/labs/lab1/my-tasks/": {
        body: [
          {
            id: "t9",
            project: "p1",
            project_name: "Alpha",
            title: "Write the methods",
            due_date: "2020-01-01",
            status: "todo",
          },
        ],
      },
    });
    renderRoute("/labs/lab1");
    expect(await screen.findByRole("link", { name: "Write the methods" })).toHaveAttribute(
      "href",
      "/labs/lab1/projects/p1/tasks?task=t9",
    );
    expect(screen.getByText("Overdue")).toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith("/dashboard/"))).toBe(false);
    expect(calls.some((c) => c.path.includes("/contributions/"))).toBe(false);
  });
});
