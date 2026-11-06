import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PARTICIPANT_WARNING, SECTIONS, totals } from "@/lib/workflow";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const user = { id: "u1", email: "ada@uni.edu", display_name: "Ada" };
const P = "/api/labs/lab1/projects/p1";
const W = "/labs/lab1/projects/p1/workflow";
const project = (perms: string[], extra: Record<string, unknown> = {}) => ({
  id: "p1",
  name: "Gut study",
  description: "About the gut",
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
  ...extra,
});
const LEAD = ["view_project", "edit_content", "edit_project"];
const CONTRIB = ["view_project", "edit_content"];
const base = (perms: string[], labPerms = ["view_lab"], extra: Record<string, unknown> = {}) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(labPerms)] },
  "GET /api/labs/lab1/": { body: makeLab(labPerms) },
  "GET /api/labs/lab1/projects/": { body: [project(perms)] },
  [`GET ${P}/`]: { body: project(perms) },
  [`GET ${P}/documents/`]: { body: [] },
  "GET /api/labs/lab1/members/": { body: [{ id: "m1", user, role: "pi" }] },
  ...extra,
});
const funding = {
  id: "f1",
  project: "p1",
  funder: "NSERC",
  program: "Discovery",
  award_number: "RGPIN-1",
  amount: "12500.50",
  currency: "CAD",
  start_date: "2030-01-01",
  end_date: "2031-01-01",
  status: "awarded",
  holder: user,
  notes: "",
  attachment: null,
  created_by: user,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

afterEach(() => vi.unstubAllGlobals());

describe("Workflow tab", () => {
  it("lists the sub-tabs in order and opens on Funding", async () => {
    mockFetch(base(CONTRIB, ["view_lab"], { [`GET ${P}/funding/`]: { body: [] } }));
    const router = renderRoute("/labs/lab1/projects/p1/workflow");
    const nav = await screen.findByRole("navigation", { name: "Workflow sections" });
    expect(
      within(nav)
        .getAllByRole("link")
        .map((l) => l.textContent),
    ).toEqual(SECTIONS.map(([, l]) => l));
    expect(SECTIONS.map(([, l]) => l)).toEqual([
      "Funding",
      "Ethics",
      "Participants",
      "Data",
      "Analysis",
      "Manuscript",
      "Review",
    ]);
    await waitFor(() => expect(router.state.location.pathname).toBe(`${W}/funding`));
    const tabs = screen.getByRole("navigation", { name: "Project sections" });
    expect(within(tabs).getByRole("link", { name: "Workflow" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Research" })).not.toBeInTheDocument();
  });

  it.each([
    ["/research", `${W}/data`],
    ["/research/datasets", `${W}/data`],
    ["/research/analyses", `${W}/analysis`],
    ["/research/results/r1", `${W}/analysis/results/r1`],
    ["/research/decisions", `${W}/review`],
    ["/research/manuscripts/new", `${W}/manuscript/manuscripts/new`],
  ])("redirects the old %s address", async (old, expected) => {
    mockFetch(
      base(CONTRIB, ["view_lab"], {
        [`GET ${P}/datasets/`]: { body: [] },
        [`GET ${P}/analyses/`]: { body: [] },
        [`GET ${P}/results/`]: { body: [] },
        [`GET ${P}/manuscripts/`]: { body: [] },
        [`GET ${P}/decisions/`]: { body: [] },
        [`GET ${P}/review-items/`]: { body: [] },
        "GET /api/labs/lab1/results/r1/": { status: 404, body: { detail: "Not found." } },
        [`GET ${P}/members/`]: { body: [] },
        [`GET ${P}/attachments/`]: { body: [] },
      }),
    );
    const router = renderRoute(`/labs/lab1/projects/p1${old}`);
    await waitFor(() => expect(router.state.location.pathname).toBe(expected));
  });

  it("keeps the breadcrumb trail through Workflow", async () => {
    mockFetch(base(CONTRIB, ["view_lab"], { [`GET ${P}/datasets/`]: { body: [] } }));
    renderRoute(`${W}/data`);
    const crumbs = await screen.findByRole("navigation", { name: /breadcrumb/i });
    expect(within(crumbs).getByText("Workflow")).toBeInTheDocument();
    expect(within(crumbs).getByText("Data")).toBeInTheDocument();
  });
});

describe("Funding", () => {
  it("shows amounts to leads and saves a new record with them", async () => {
    const calls = mockFetch(
      base(LEAD, ["view_lab"], {
        [`GET ${P}/funding/`]: { body: [funding] },
        [`GET ${P}/attachments/`]: { body: [] },
        [`POST ${P}/funding/`]: { status: 201, body: funding },
      }),
    );
    renderRoute(`${W}/funding`);
    expect(await screen.findByText("NSERC")).toBeInTheDocument();
    expect(screen.getByText(/12,500\.50/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add funding" }));
    await userEvent.type(await screen.findByLabelText("Funder"), "CIHR");
    await userEvent.type(screen.getByLabelText("Amount"), "900");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({
      funder: "CIHR",
      amount: "900",
      currency: "CAD",
      status: "applied",
    });
  });

  it("hides the amount column and field from people who are not leads", async () => {
    mockFetch(
      base(CONTRIB, ["view_lab"], {
        [`GET ${P}/funding/`]: { body: [{ ...funding, amount: null, currency: null }] },
        [`GET ${P}/attachments/`]: { body: [] },
        [`POST ${P}/funding/`]: { status: 201, body: funding },
      }),
    );
    renderRoute(`${W}/funding`);
    expect(await screen.findByText("NSERC")).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Amount" })).not.toBeInTheDocument();
    expect(screen.getByText("Amounts are visible to project leads only.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Edit NSERC" }));
    await screen.findByLabelText("Funder");
    expect(screen.queryByLabelText("Amount")).not.toBeInTheDocument();
  });

  it("asks for a funder before saving", async () => {
    const calls = mockFetch(
      base(CONTRIB, ["view_lab"], {
        [`GET ${P}/funding/`]: { body: [] },
        [`GET ${P}/attachments/`]: { body: [] },
      }),
    );
    renderRoute(`${W}/funding`);
    await userEvent.click(await screen.findByRole("button", { name: "Add funding" }));
    await userEvent.click(await screen.findByRole("button", { name: "Save" }));
    expect(await screen.findByText("Enter the funder")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });
});

describe("Ethics", () => {
  const approval = {
    id: "ap1",
    approval_number: "IRB-1",
    board: "Example IRB",
    title: "Gut microbiome",
    approval_date: "2026-01-01",
    expiry_date: "2099-01-01",
    status: "active",
    restricted: false,
    projects: [{ id: "p1", name: "Gut study" }],
    attachments: [],
    can_view_files: true,
    created_by: user,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
  const LAB = ["view_lab", "view_ethics", "edit_ethics", "manage_lab"];

  it("lists the project's approvals, the institution's links and a lab-wide link", async () => {
    mockFetch(
      base(CONTRIB, LAB, {
        "GET /api/labs/lab1/ethics-approvals/?project=p1": { body: [approval] },
        "GET /api/labs/lab1/institution-resources/?category=ethics": {
          body: [
            {
              id: "r1",
              category: "ethics",
              title: "Research Ethics Office",
              url: "https://example.edu/ethics",
              description: "Apply for approval",
              order: 0,
            },
          ],
        },
      }),
    );
    renderRoute(`${W}/ethics`);
    expect(await screen.findByRole("link", { name: /IRB-1: Gut microbiome/ })).toHaveAttribute(
      "href",
      "/labs/lab1/ethics/ap1",
    );
    expect(await screen.findByRole("link", { name: /Research Ethics Office/ })).toHaveAttribute(
      "href",
      "https://example.edu/ethics",
    );
    expect(screen.getByRole("link", { name: "See every approval in the lab" })).toHaveAttribute(
      "href",
      "/labs/lab1/ethics",
    );
  });

  it("copes with the institution endpoint not existing", async () => {
    mockFetch(
      base(CONTRIB, LAB, {
        "GET /api/labs/lab1/ethics-approvals/?project=p1": { body: [] },
        "GET /api/labs/lab1/institution-resources/?category=ethics": {
          status: 404,
          body: { detail: "Not found." },
        },
      }),
    );
    renderRoute(`${W}/ethics`);
    expect(await screen.findByText("No ethics approvals linked yet")).toBeInTheDocument();
    expect(screen.queryByText(/Ethics resources at your institution/)).not.toBeInTheDocument();
  });

  it("links a new approval to the project", async () => {
    const calls = mockFetch(
      base(CONTRIB, LAB, {
        "GET /api/labs/lab1/ethics-approvals/?project=p1": { body: [] },
        "GET /api/labs/lab1/institution-resources/?category=ethics": { body: [] },
        "POST /api/labs/lab1/ethics-approvals/": { status: 201, body: approval },
      }),
    );
    renderRoute(`${W}/ethics`);
    await userEvent.click(await screen.findByRole("button", { name: "New approval" }));
    await userEvent.type(await screen.findByLabelText("Approval number"), "IRB-9");
    await userEvent.type(screen.getByLabelText("Ethics board"), "REB");
    await userEvent.type(screen.getByLabelText("Title"), "New study");
    await userEvent.type(screen.getByLabelText("Approval date"), "2026-01-01");
    await userEvent.type(screen.getByLabelText("Expiry date"), "2027-01-01");
    await userEvent.click(screen.getByRole("checkbox", { name: /Restricted/ }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({
      approval_number: "IRB-9",
      projects: ["p1"],
      restricted: true,
    });
  });
});

describe("Participants", () => {
  const entry = (id: string, status: string, count: number) => ({
    id,
    project: "p1",
    entry_date: "2030-02-01",
    status,
    count,
    notes: "",
    created_by: user,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  });
  const mocks = (extra: Record<string, unknown> = {}) =>
    base(CONTRIB, ["view_lab"], {
      [`GET ${P}/recruitment-entries/`]: {
        body: [entry("e1", "screened", 10), entry("e2", "enrolled", 7), entry("e3", "enrolled", 3)],
      },
      [`GET ${P}/recruitment-plan/`]: { body: { target_enrolment: 20, notes: "Rolling intake" } },
      [`GET ${P}/external-links/`]: { body: [] },
      "GET /api/labs/lab1/integrations/providers/": { body: [] },
      ...extra,
    });

  it("always shows the no-personal-data warning, with the totals", async () => {
    mockFetch(mocks());
    renderRoute(`${W}/participants`);
    expect(await screen.findByRole("note")).toHaveTextContent(PARTICIPANT_WARNING);
    expect(PARTICIPANT_WARNING).toBe(
      "Don't enter names or identifying details here; keep participant records in REDCap or your approved system",
    );
    expect(await screen.findByText("10 of 20 enrolled (50%).")).toBeInTheDocument();
    expect(screen.getByText("Rolling intake")).toBeInTheDocument();
    const tile = screen.getByText("Enrolled", { selector: "dt" }).parentElement!;
    expect(tile).toHaveTextContent("10");
  });

  it("adds a dated entry and shows the warning in the form", async () => {
    const calls = mockFetch(
      mocks({
        [`POST ${P}/recruitment-entries/`]: { status: 201, body: entry("e4", "screened", 4) },
      }),
    );
    renderRoute(`${W}/participants`);
    await userEvent.click(await screen.findByRole("button", { name: "Add entry" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("note")).toHaveTextContent(PARTICIPANT_WARNING);
    await userEvent.type(within(dialog).getByLabelText("Number of people"), "4");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({
      status: "screened",
      count: 4,
    });
  });

  it("shows server complaints about personal data under the field", async () => {
    mockFetch(
      mocks({
        [`POST ${P}/recruitment-entries/`]: {
          status: 400,
          body: {
            notes: [
              "Don't enter names or identifying details here (that looks like an email address).",
            ],
          },
        },
      }),
    );
    renderRoute(`${W}/participants`);
    await userEvent.click(await screen.findByRole("button", { name: "Add entry" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Number of people"), "1");
    await userEvent.type(within(dialog).getByLabelText("Notes (optional)"), "a@b.co");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await within(dialog).findByText(/looks like an email address/)).toBeInTheDocument();
  });

  it("lists only REDCap and Qualtrics links", async () => {
    const link = (id: string, provider: string, title: string) => ({
      id,
      provider,
      title,
      url: `https://example.org/${id}`,
      status: "ok",
      document: null,
      dataset: null,
      analysis: null,
      result: null,
      manuscript: null,
      decision: null,
      linked_by: user,
      linked_at: "2026-01-01T00:00:00Z",
      linked_modified_at: null,
      remote_modified_at: null,
    });
    mockFetch(
      mocks({
        [`GET ${P}/external-links/`]: {
          body: [link("l1", "redcap", "Intake survey"), link("l2", "github", "Some repo")],
        },
      }),
    );
    renderRoute(`${W}/participants`);
    expect(await screen.findByText("Intake survey")).toBeInTheDocument();
    expect(screen.queryByText("Some repo")).not.toBeInTheDocument();
  });

  it("sums entries per status", () => {
    expect(
      totals([
        { status: "enrolled", count: 2 },
        { status: "enrolled", count: 3 },
        { status: "withdrawn", count: 1 },
      ]),
    ).toEqual({ screened: 0, enrolled: 5, withdrawn: 1, completed: 0 });
  });
});

describe("Review", () => {
  it("lists review items and the decisions under them", async () => {
    const item = {
      id: "rv1",
      project: "p1",
      title: "Methods sign-off",
      reviewer: user,
      status: "changes_requested",
      due_date: "2030-03-01",
      notes: "Fix section 2",
      created_by: user,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    const decision = {
      id: "dc1",
      project: "p1",
      title: "Use rarefaction",
      rationale: "",
      decided_on: "2026-03-01",
      decided_by: user,
      supporting_documents: [],
      supporting_attachments: [],
      references: [],
      analyses: [],
      results: [],
      datasets: [],
      created_at: "2026-03-01T00:00:00Z",
      updated_at: "2026-03-01T00:00:00Z",
    };
    const calls = mockFetch(
      base(CONTRIB, ["view_lab"], {
        [`GET ${P}/review-items/`]: { body: [item] },
        [`GET ${P}/decisions/`]: { body: [decision] },
        "PATCH /api/labs/lab1/review-items/rv1/": { body: item },
      }),
    );
    renderRoute(`${W}/review`);
    expect(await screen.findByText("Methods sign-off")).toBeInTheDocument();
    expect(screen.getByText("Changes requested")).toBeInTheDocument();
    expect(await screen.findByText("Use rarefaction")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Edit Methods sign-off" }));
    await userEvent.selectOptions(await screen.findByLabelText("Status"), "approved");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")!.body).toMatchObject({
      status: "approved",
      reviewer: "u1",
    });
  });
});

describe("Overview", () => {
  const deadline = (id: string, title: string, priority: string) => ({
    id,
    project: "p1",
    title,
    due_date: "2030-01-01",
    done: false,
    priority,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  });

  it("colours deadline priorities and keeps the server order", async () => {
    mockFetch(
      base(LEAD, ["view_lab"], {
        [`GET ${P}/deadlines/`]: {
          body: [
            deadline("d1", "Submit", "high"),
            deadline("d2", "Tidy", "low"),
            deadline("d3", "Review", "medium"),
          ],
        },
        [`GET ${P}/members/`]: { body: [] },
      }),
    );
    renderRoute("/labs/lab1/projects/p1/overview");
    await screen.findByText("Submit");
    const badge = (name: string) => screen.getByText(name, { selector: "span" });
    expect(badge("High").className).toContain("bg-danger");
    expect(badge("Medium").className).toContain("bg-warning");
    expect(badge("Low").className).toContain("bg-success");
    const rows = screen.getAllByRole("row").map((r) => r.textContent ?? "");
    expect(rows.findIndex((r) => r.includes("Submit"))).toBeLessThan(
      rows.findIndex((r) => r.includes("Tidy")),
    );
  });

  it("edits a deadline's priority", async () => {
    const calls = mockFetch(
      base(LEAD, ["view_lab"], {
        [`GET ${P}/deadlines/`]: { body: [deadline("d1", "Submit", "medium")] },
        [`GET ${P}/members/`]: { body: [] },
        "PATCH /api/labs/lab1/deadlines/d1/": { body: deadline("d1", "Submit", "high") },
      }),
    );
    renderRoute("/labs/lab1/projects/p1/overview");
    await userEvent.click(await screen.findByRole("button", { name: "Edit Submit" }));
    await userEvent.selectOptions(await screen.findByLabelText("Priority"), "high");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")!.body).toMatchObject({
      title: "Submit",
      priority: "high",
    });
  });

  it("shows when and by whom the project was last edited, with the full date on hover", async () => {
    const at = new Date(Date.now() - 3 * 3600 * 1000).toISOString();
    mockFetch({
      ...base(CONTRIB),
      [`GET ${P}/`]: {
        body: project(CONTRIB, {
          last_activity_at: at,
          last_activity_by: { ...user, display_name: "Grace" },
        }),
      },
      [`GET ${P}/deadlines/`]: { body: [] },
      [`GET ${P}/members/`]: { body: [] },
    });
    renderRoute("/labs/lab1/projects/p1/overview");
    const line = await screen.findByText(/Last edited/);
    expect(line).toHaveTextContent("Last edited 3 hours ago by Grace");
    expect(within(line).getByText("3 hours ago")).toHaveAttribute(
      "title",
      expect.stringMatching(/\d{4}/),
    );
  });

  it("shows nothing when there is no recorded edit", async () => {
    mockFetch({
      ...base(CONTRIB),
      [`GET ${P}/deadlines/`]: { body: [] },
      [`GET ${P}/members/`]: { body: [] },
    });
    renderRoute("/labs/lab1/projects/p1/overview");
    await screen.findByText("About the gut");
    expect(screen.queryByText(/Last edited/)).not.toBeInTheDocument();
  });
});
