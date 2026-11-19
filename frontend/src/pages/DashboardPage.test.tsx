import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { localDateISO } from "@/lib/format";
import { addDays } from "@/lib/snooze";
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
      in_progress_tasks: 1,
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
  "GET /api/labs/lab1/training/compliance/": { status: 404, body: { detail: "Not found." } },
  "GET /api/labs/lab1/contributions/": { body: contributions() },
  "GET /api/labs/lab1/my-tasks/": { body: [] },
  "GET /api/labs/lab1/start-here/": { body: [] },
  "GET /api/labs/lab1/my-onboarding/": { body: [] },
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
    expect(screen.queryByText(/Training needs attention/)).not.toBeInTheDocument();
    // the overdue tasks are listed without opening the card
    expect(within(overdue).getByRole("link", { name: "Order reagents" })).toBeVisible();
    expect(within(overdue).queryByRole("link", { name: /Review/ })).toBeNull();
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

  const cell = (status: string, days: number | null = null) => ({
    status,
    record: null,
    completed_on: null,
    expires_on: null,
    days_left: days,
    verified: false,
  });
  const compliance = {
    requirements: [{ id: "r1", name: "Biosafety" }],
    members: [
      {
        user: { id: "u2", email: "bo@uni.edu", display_name: "Bo" },
        role: "member",
        cells: { r1: cell("expiring", 26) },
      },
      {
        user: { id: "u3", email: "cy@uni.edu", display_name: "Cy" },
        role: "member",
        cells: { r1: cell("missing") },
      },
      {
        user: { id: "u4", email: "di@uni.edu", display_name: "Di" },
        role: "member",
        cells: { r1: cell("done", 300) },
      },
    ],
    summary: { done: 1, expiring: 1, expired: 0, missing: 1 },
  };

  it("counts missing training too, not only what is expiring", async () => {
    mockFetch({ ...base(dash()), "GET /api/labs/lab1/training/compliance/": { body: compliance } });
    renderRoute("/labs/lab1/dashboard");
    const card = await screen.findByRole("region", {
      name: /Training needs attention \(expired, expiring or missing\)/,
    });
    expect(within(card).getByText("2")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Biosafety · Bo" })).toHaveAttribute(
      "href",
      "/labs/lab1/training",
    );
    expect(within(card).getByText("No record yet")).toBeInTheDocument();
    expect(within(card).queryByText(/Di/)).toBeNull();
  });

  it("lists low stock for people who manage inventory", async () => {
    const perms = [...PI, "manage_inventory"];
    mockFetch({
      ...base(dash(), perms),
      "GET /api/labs/lab1/": { body: { ...makeLab(perms), inventory_enabled: true } },
      "GET /api/labs/lab1/inventory/": {
        body: [
          {
            id: "i1",
            name: "Pipette tips",
            quantity: "2",
            unit: "boxes",
            low_stock_at: "5",
            low: true,
            owner: null,
          },
          {
            id: "i2",
            name: "Gloves",
            quantity: "40",
            unit: "boxes",
            low_stock_at: "5",
            low: false,
            owner: null,
          },
        ],
      },
    });
    renderRoute("/labs/lab1/dashboard");
    const card = await screen.findByRole("region", { name: /Low stock/ });
    expect(within(card).getByRole("link", { name: "Pipette tips" })).toHaveAttribute(
      "href",
      "/labs/lab1/inventory",
    );
    expect(within(card).queryByText("Gloves")).toBeNull();
  });

  it("narrows Needs attention to your own with Mine only", async () => {
    const mine = dash() as { attention: Record<string, unknown> };
    mine.attention.overdue_tasks = list(
      [
        {
          id: "t1",
          title: "Order reagents",
          due_date: "2026-11-01",
          days_overdue: 4,
          project_id: "p2",
          project_name: "Beta",
          assignee: { id: "u1", name: "Ada" },
        },
        {
          id: "t2",
          title: "Fix the rig",
          due_date: "2026-11-01",
          days_overdue: 4,
          project_id: "p2",
          project_name: "Beta",
          assignee: { id: "u9", name: "Zed" },
        },
      ],
      2,
    );
    mockFetch({
      ...base(mine),
      "GET /api/me/": { body: { id: "u1", email: "ada@uni.edu", display_name: "Ada" } },
    });
    renderRoute("/labs/lab1/dashboard");
    await screen.findByRole("link", { name: "Fix the rig" });
    await userEvent.click(screen.getByRole("button", { name: "Mine only" }));
    expect(screen.queryByRole("link", { name: "Fix the rig" })).toBeNull();
    expect(screen.getByRole("link", { name: "Order reagents" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Pilot REB/ })).toBeNull();
  });

  it("shows the next meeting with its time and a way in", async () => {
    const starts = new Date(Date.now() + 2 * 3600_000).toISOString();
    mockFetch({
      ...base(dash()),
      [`GET /api/labs/lab1/calendar/?from=${localDateISO()}&to=${addDays(localDateISO(), 30)}`]: {
        body: [
          {
            kind: "meeting",
            id: "m1",
            title: "Lab meeting",
            date: localDateISO(),
            starts_at: starts,
            ends_at: null,
            join_url: "https://meet.example.test/abc",
            notes: "",
          },
        ],
      },
    });
    renderRoute("/labs/lab1/dashboard");
    const section = await screen.findByRole("region", { name: "Next meeting" });
    expect(within(section).getByRole("link", { name: "Lab meeting" })).toHaveAttribute(
      "href",
      "/labs/lab1/calendar",
    );
    expect(within(section).getByRole("link", { name: /Join call/ })).toHaveAttribute(
      "href",
      "https://meet.example.test/abc",
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

  it("gives a new member Start here, their onboarding with ticks, and their projects", async () => {
    const item = (over: Record<string, unknown>) => ({
      id: "o1",
      title: "Read the SOP",
      description: "",
      url: "https://example.test/sop",
      required: true,
      done: false,
      by_training: false,
      training_requirement_name: "",
      ...over,
    });
    const calls = mockFetch({
      ...base(dash(), ["view_lab", "create_project"]),
      "GET /api/labs/lab1/projects/": {
        body: [{ id: "p1", name: "Alpha", status: "active", updated_at: "2026-11-01T00:00:00Z" }],
      },
      "GET /api/labs/lab1/start-here/": {
        body: [
          {
            id: "d1",
            title: "Lab manual",
            project: null,
            project_name: "",
            embed_url: "",
            can_manage: false,
          },
        ],
      },
      "GET /api/labs/lab1/my-onboarding/": {
        body: [item({}), item({ id: "o2", title: "Badge", url: "" })],
      },
      "POST /api/labs/lab1/my-onboarding/o1/": { body: item({ done: true }) },
    });
    renderRoute("/labs/lab1");
    expect(await screen.findByRole("link", { name: "Lab manual" })).toHaveAttribute(
      "href",
      "/labs/lab1/documents/d1",
    );
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull(); // not a manager
    expect(await screen.findByRole("heading", { name: "Your projects" })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Alpha" }).length).toBeGreaterThan(1); // + sidebar
    expect(screen.getByText("0 of 2 done")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute(
      "href",
      "https://example.test/sop",
    );
    await userEvent.click(screen.getByRole("checkbox", { name: "Read the SOP" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({ done: true }),
    );
  });

  it("does not show a manager the member onboarding card", async () => {
    const calls = mockFetch(base(dash()));
    renderRoute("/labs/lab1");
    await screen.findByRole("heading", { name: "Needs attention" });
    expect(calls.some((c) => c.path.includes("/my-onboarding/"))).toBe(false);
  });

  it("counts a past-due deadline as overdue and says how late it is", async () => {
    mockFetch(
      base(
        dash({
          projects: [
            project({
              id: "p3",
              name: "Paper 2",
              overdue_deadlines: 1,
              health: "red",
              health_reasons: ["1 overdue deadline"],
              next_deadline: {
                id: "d1",
                title: "Submit draft",
                due_date: ago(4),
                priority: "high",
              },
            }),
          ],
        }),
      ),
    );
    renderRoute("/labs/lab1");
    const row = (await screen.findByRole("link", { name: "Paper 2" })).closest("tr")!;
    expect(within(row).getByText("4 days overdue", { exact: false })).toBeInTheDocument();
    expect(within(row).getByTitle(/1 overdue deadlines/)).toHaveTextContent("1");
  });

  it("keeps completed projects out of the table until asked for", async () => {
    mockFetch(
      base(
        dash({
          projects: [
            project({ name: "Live one" }),
            project({ id: "p9", name: "OILERS", status: "completed" }),
          ],
        }),
      ),
    );
    renderRoute("/labs/lab1");
    await screen.findByRole("link", { name: "Live one" });
    expect(screen.queryByRole("link", { name: "OILERS" })).toBeNull();
    await userEvent.click(
      screen.getByRole("button", { name: /Show completed and archived \(1\)/ }),
    );
    expect(await screen.findByRole("link", { name: "OILERS" })).toBeInTheDocument();
  });

  it("snoozes a kind of problem and brings it back on request", async () => {
    mockFetch(base(dash()));
    renderRoute("/labs/lab1");
    const card = await screen.findByRole("region", { name: /Ethics approvals/ });
    expect(within(card).getByRole("link", { name: /Renew/ })).toHaveAttribute(
      "href",
      "/labs/lab1/ethics",
    );
    await userEvent.click(within(card).getByRole("button", { name: "Snooze for a week" }));
    expect(screen.queryByRole("region", { name: /Ethics approvals/ })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Show them again" }));
    expect(await screen.findByRole("region", { name: /Ethics approvals/ })).toBeInTheDocument();
  });
});
