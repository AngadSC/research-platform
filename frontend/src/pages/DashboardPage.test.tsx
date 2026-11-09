import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

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
        expiry_date: "2026-11-01",
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
});

afterEach(() => vi.unstubAllGlobals());

describe("Dashboard", () => {
  it("is the landing page for a PI, with tiles, cards, table and people", async () => {
    mockFetch(base(dash()));
    renderRoute("/labs/lab1");
    const summary = await screen.findByRole("region", { name: "Summary" });
    expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument(); // sidebar entry
    expect(within(summary).getByText("Overdue tasks").nextSibling).toHaveTextContent("3");
    const overdue = screen.getByRole("region", { name: /Overdue tasks/ });
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
    // empty cards say so, and training stays hidden when its endpoint is unavailable
    expect(screen.getByText("No deadlines in the next 14 days.")).toBeInTheDocument();
    expect(screen.queryByText("Training expiring")).not.toBeInTheDocument();
  });

  it("sorts the project table", async () => {
    mockFetch(base(dash()));
    renderRoute("/labs/lab1/dashboard");
    await screen.findByRole("region", { name: "Summary" });
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

  it("shows empty states for a lab with no projects", async () => {
    const empty = dash({
      projects: [],
      summary: { ...dash().summary, overdue_tasks: 0, ethics_attention: 0 },
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
    mockFetch(base(empty));
    renderRoute("/labs/lab1/dashboard");
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
    expect(screen.getByText("Nothing is overdue.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New project" })).toHaveAttribute(
      "href",
      "/labs/lab1/projects?new=project",
    );
  });

  it("shows a loading skeleton first", async () => {
    mockFetch(base(dash()));
    renderRoute("/labs/lab1/dashboard");
    expect(await screen.findByLabelText("Loading dashboard")).toBeInTheDocument();
    await screen.findByRole("region", { name: "Summary" });
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

  it("does not offer the dashboard to a member, and keeps their project list", async () => {
    const calls = mockFetch(base(dash(), ["view_lab", "create_project"]));
    renderRoute("/labs/lab1");
    expect(await screen.findByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Dashboard" })).not.toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith("/dashboard/"))).toBe(false);
    expect(calls.some((c) => c.path.includes("/contributions/"))).toBe(false);
  });
});
