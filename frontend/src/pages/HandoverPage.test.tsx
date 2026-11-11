import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const ada = { id: "u1", email: "ada@uni.edu", display_name: "Ada" };
const grace = { id: "u2", email: "grace@uni.edu", display_name: "Grace" };
const at = "2026-01-01T00:00:00Z";
const members = [
  { id: "m1", user: ada, role: "member", created_at: at },
  { id: "m2", user: grace, role: "member", created_at: at },
];
const item = (title: string, kind = "project") => ({
  id: kind === "project" ? "p1" : title,
  kind,
  title,
  project: { id: "p1", name: "Gut study" },
  href: "/labs/lab1/projects/p1/overview",
  reason: "They are the only lead.",
});
const report = (orphans: unknown[]) => ({
  generated_at: "2026-11-04T10:00:00Z",
  person: { id: "u2", membership_id: "m2", display_name: "Grace", email: "grace@uni.edu" },
  project: null,
  no_other_owner: orphans,
  sections: [
    { key: "open_tasks", label: "Open tasks", items: [item("Fit model", "task")] },
    {
      key: "unassigned_tasks",
      label: "Unassigned after access change",
      items: [item("Clean data", "task")],
    },
    { key: "datasets", label: "Datasets", items: [] },
  ],
});
const base = (perms: string[]) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [] },
  "GET /api/me/": { body: ada },
  "GET /api/labs/lab1/": { body: makeLab(perms) },
  "GET /api/labs/lab1/members/": { body: members },
});

describe("handover report", () => {
  it("shows the No other owner callout above the sections when items exist", async () => {
    mockFetch({
      ...base(["view_lab", "manage_members"]),
      "GET /api/labs/lab1/members/m2/handover/": { body: report([item("Archived Survey")]) },
    });
    renderRoute("/labs/lab1/members/m2/handover");
    const callout = await screen.findByRole("region", { name: /No other owner/ });
    expect(within(callout).getByRole("link", { name: "Archived Survey" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Open tasks (1)" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Unassigned after access change (1)" }),
    ).toBeInTheDocument();
    expect(screen.getByText("No datasets")).toBeInTheDocument(); // empty section
    expect(screen.getByRole("button", { name: /Print or save as PDF/ })).toBeInTheDocument();
  });

  it("omits the callout when nothing lacks another owner", async () => {
    mockFetch({
      ...base(["view_lab", "manage_members"]),
      "GET /api/labs/lab1/members/m2/handover/": { body: report([]) },
    });
    renderRoute("/labs/lab1/members/m2/handover");
    expect(await screen.findByRole("heading", { name: "Open tasks (1)" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /No other owner/ })).not.toBeInTheDocument();
  });
});

describe("role explanations", () => {
  it("explains a role on keyboard focus", async () => {
    mockFetch(base(["view_lab"]));
    renderRoute("/labs/lab1/members");
    await screen.findByText("Grace");
    screen.getAllByRole("button", { name: "Member" })[0]!.focus();
    expect(await screen.findByRole("tooltip")).toHaveTextContent(/Can start projects/);
  });
});

describe("handover actions", () => {
  it("hides Work to pass on without manage_members but offers My work to pass on", async () => {
    mockFetch(base(["view_lab"]));
    renderRoute("/labs/lab1/members");
    expect(await screen.findByText("Grace")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /My work to pass on/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Work to pass on/ })).not.toBeInTheDocument();
  });

  it("shows Work to pass on for other members with manage_members", async () => {
    mockFetch(base(["view_lab", "manage_members"]));
    renderRoute("/labs/lab1/members");
    const link = await screen.findByRole("link", { name: /^Work to pass on for grace@uni.edu/ });
    expect(link).toHaveAttribute("href", "/labs/lab1/members/m2/handover");
  });

  const project = (perms: string[]) => ({
    id: "p1",
    name: "Gut study",
    description: "",
    status: "active",
    start_date: null,
    retain_until: null,
    retention_note: "",
    created_by: ada,
    created_at: at,
    updated_at: at,
    my_project_role: "lead",
    my_permissions: perms,
  });
  const overview = (perms: string[]) => ({
    ...base(["view_lab"]),
    "GET /api/labs/lab1/projects/": { body: [project(perms)] },
    "GET /api/labs/lab1/projects/p1/": { body: project(perms) },
    "GET /api/labs/lab1/projects/p1/deadlines/": { body: [] },
    "GET /api/labs/lab1/projects/p1/members/": {
      body: [{ id: "pm1", project: "p1", user: grace, role: "contributor", created_at: at }],
    },
  });

  it("hides the project member action without manage_project_members", async () => {
    mockFetch(overview(["view_project"]));
    renderRoute("/labs/lab1/projects/p1/overview");
    expect(await screen.findByText("Grace")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Work to pass on/ })).not.toBeInTheDocument();
  });

  it("shows the project member action with manage_project_members", async () => {
    mockFetch(overview(["view_project", "manage_project_members"]));
    renderRoute("/labs/lab1/projects/p1/overview");
    const link = await screen.findByRole("link", { name: /^Work to pass on for grace@uni.edu/ });
    expect(link).toHaveAttribute("href", "/labs/lab1/projects/p1/handover?user=u2");
  });
});

describe("reassign from the list", () => {
  const tasks = (...titles: string[]) => titles.map((t) => item(t, "task"));
  const rep = (open: string[], orphans: unknown[] = []) => ({
    ...report(orphans),
    sections: [{ key: "open_tasks", label: "Open tasks", items: tasks(...open) }],
  });
  const grp = { id: "u3", email: "alex@uni.edu", display_name: "Alex" };
  const all = [
    ...members,
    { id: "m3", user: grp, role: "member", created_at: at },
    {
      id: "m4",
      user: { id: "u4", email: "v@uni.edu", display_name: "Vera" },
      role: "viewer",
      created_at: at,
    },
  ];
  const setup = (
    perms: string[],
    extra: Record<string, unknown> = {},
    open = ["A", "B"],
    orphans: unknown[] = [],
  ) => {
    let current = rep(open, orphans);
    const calls = mockFetch({
      ...base(perms),
      "GET /api/labs/lab1/members/": { body: all },
      "GET /api/labs/lab1/members/m2/handover/": () => ({ body: current }),
      ...extra,
    } as never);
    return { calls, set: (r: typeof current) => (current = r) };
  };
  const pick = async (label: RegExp | string, name: string) => {
    await userEvent.click(await screen.findByRole("combobox", { name: label }));
    await userEvent.click(await screen.findByRole("option", { name }));
  };

  it("hides the controls without manage_members", async () => {
    setup(["view_lab"]);
    renderRoute("/labs/lab1/members/m2/handover");
    await screen.findByRole("heading", { name: "Open tasks (2)" });
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("shows a skeleton while loading", async () => {
    setup(["view_lab", "manage_members"]);
    renderRoute("/labs/lab1/members/m2/handover");
    expect(await screen.findByLabelText("Loading")).toHaveAttribute("aria-busy", "true");
    await screen.findByRole("heading", { name: "Open tasks (2)" });
  });

  it("offers everyone except the departing person and viewers", async () => {
    setup(["view_lab", "manage_members"]);
    renderRoute("/labs/lab1/members/m2/handover");
    await userEvent.click(await screen.findByRole("combobox", { name: /Reassign all open tasks/ }));
    const names = (await screen.findAllByRole("option")).map((o) => o.textContent);
    expect(names).toEqual(["Ada", "Alex"]);
  });

  it("sends one PATCH per task, then refetches", async () => {
    const { calls, set } = setup(["view_lab", "manage_members"], {
      "PATCH /api/labs/lab1/tasks/A/": { body: {} },
      "PATCH /api/labs/lab1/tasks/B/": { body: {} },
    });
    renderRoute("/labs/lab1/members/m2/handover");
    await screen.findByRole("heading", { name: "Open tasks (2)" });
    await pick(/Reassign all open tasks/, "Alex");
    set(rep([]));
    await userEvent.click(screen.getByRole("button", { name: "Reassign all to…" }));
    expect(await screen.findByRole("heading", { name: "Open tasks (0)" })).toBeInTheDocument();
    const patches = calls.filter((c) => c.method === "PATCH");
    expect(patches.map((c) => [c.path, c.body])).toEqual([
      ["/api/labs/lab1/tasks/A/", { assignee: "u3" }],
      ["/api/labs/lab1/tasks/B/", { assignee: "u3" }],
    ]);
  });

  it("keeps failed rows with the server message", async () => {
    const { set } = setup(["view_lab", "manage_members"], {
      "PATCH /api/labs/lab1/tasks/A/": { body: {} },
      "PATCH /api/labs/lab1/tasks/B/": {
        status: 400,
        body: { assignee: ["Alex is not on this project."] },
      },
    });
    renderRoute("/labs/lab1/members/m2/handover");
    await screen.findByRole("heading", { name: "Open tasks (2)" });
    await pick(/Reassign all open tasks/, "Alex");
    set(rep(["B"]));
    await userEvent.click(screen.getByRole("button", { name: "Reassign all to…" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Alex is not on this project.");
    expect(screen.getByRole("heading", { name: "Open tasks (1)" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "B" })).toBeInTheDocument();
  });

  it("adds a lead through the project members endpoint", async () => {
    const { calls } = setup(
      ["view_lab", "manage_members"],
      {
        "GET /api/labs/lab1/projects/p1/members/": { body: [] },
        "POST /api/labs/lab1/projects/p1/members/": { body: {} },
      },
      ["A"],
      [item("Gut study")],
    );
    renderRoute("/labs/lab1/members/m2/handover");
    await pick(/Add a lead for/, "Alex");
    await userEvent.click(screen.getByRole("button", { name: "Add as lead" }));
    await screen.findByRole("heading", { name: /Open tasks/ });
    const post = calls.find((c) => c.method === "POST");
    expect(post?.path).toBe("/api/labs/lab1/projects/p1/members/");
    expect(post?.body).toEqual({ user: "u3", role: "lead" });
  });
});
