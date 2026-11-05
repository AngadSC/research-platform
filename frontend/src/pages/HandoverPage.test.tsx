import { screen, within } from "@testing-library/react";
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
  id: title,
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

describe("handover actions", () => {
  it("hides Generate handover without manage_members but offers My handover", async () => {
    mockFetch(base(["view_lab"]));
    renderRoute("/labs/lab1/members");
    expect(await screen.findByText("Grace")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /My handover/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Generate handover/ })).not.toBeInTheDocument();
  });

  it("shows Generate handover for other members with manage_members", async () => {
    mockFetch(base(["view_lab", "manage_members"]));
    renderRoute("/labs/lab1/members");
    const link = await screen.findByRole("link", { name: /Generate handover for grace@uni.edu/ });
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
    expect(screen.queryByRole("link", { name: /Generate handover/ })).not.toBeInTheDocument();
  });

  it("shows the project member action with manage_project_members", async () => {
    mockFetch(overview(["view_project", "manage_project_members"]));
    renderRoute("/labs/lab1/projects/p1/overview");
    const link = await screen.findByRole("link", { name: /Generate handover for grace@uni.edu/ });
    expect(link).toHaveAttribute("href", "/labs/lab1/projects/p1/handover?user=u2");
  });
});
