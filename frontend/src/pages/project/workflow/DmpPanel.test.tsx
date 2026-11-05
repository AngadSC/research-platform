import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const user = { id: "u1", email: "ada@uni.edu", display_name: "Ada" };
const P = "/api/labs/lab1/projects/p1";
const D = `${P}/data-management-plan/`;
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
const LEAD = ["view_project", "edit_content", "edit_project"];
const CONTRIB = ["view_project", "edit_content"];
const VIEWER = ["view_project"];
const empty = {
  exists: false,
  data_description: "",
  collection: "",
  documentation: "",
  storage: "",
  preservation: "",
  sharing: "",
  responsibilities: "",
  ethics_legal: "",
  status: "draft",
  last_reviewed: null,
  external_url: "",
  attachment: null,
  approved_by: null,
  approved_at: null,
  updated_by: null,
  updated_at: "2026-01-01T00:00:00Z",
};
const saved = {
  ...empty,
  exists: true,
  storage: "Encrypted lab server",
  last_reviewed: "2026-05-01",
};
const base = (perms: string[], plan: object, extra: Record<string, unknown> = {}) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(["view_lab"])] },
  "GET /api/labs/lab1/": { body: makeLab(["view_lab"]) },
  "GET /api/labs/lab1/projects/": { body: [project(perms)] },
  [`GET ${P}/`]: { body: project(perms) },
  [`GET ${P}/documents/`]: { body: [] },
  [`GET ${P}/datasets/`]: { body: [] },
  [`GET ${P}/attachments/`]: { body: [] },
  [`GET ${D}`]: { body: plan },
  "GET /api/labs/lab1/institution-resources/?category=data_management": {
    body: [
      {
        id: "r1",
        title: "Borealis deposit guide",
        url: "https://borealisdata.ca/guide",
        description: "How to deposit",
      },
    ],
  },
  ...extra,
});
const open = () => renderRoute("/labs/lab1/projects/p1/workflow/data");

afterEach(() => vi.unstubAllGlobals());

describe("Data management plan panel", () => {
  it("sits above the datasets list and offers institution links", async () => {
    mockFetch(base(LEAD, empty));
    open();
    const panel = await screen.findByRole("region", { name: "Data management plan" });
    expect(within(panel).getByText("Not started")).toBeInTheDocument();
    expect(
      await within(panel).findByRole("link", { name: /Borealis deposit guide/ }),
    ).toHaveAttribute("href", "https://borealisdata.ca/guide");
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument(); // nothing saved
  });

  it("starts a plan with every template section and saves it", async () => {
    const calls = mockFetch(
      base(CONTRIB, empty, { [`PATCH ${D}`]: { body: { ...saved, storage: "Server" } } }),
    );
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Start plan" }));
    for (const name of [
      "Data description",
      "Data collection",
      "Documentation and metadata",
      "Storage and backup",
      "Preservation",
      "Sharing and reuse",
      "Responsibilities and resources",
      "Ethics and legal compliance",
    ])
      expect(screen.getByLabelText(name)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Storage and backup"), "Server");
    await userEvent.selectOptions(screen.getByLabelText("Status"), "submitted");
    await userEvent.click(screen.getByRole("button", { name: "Save plan" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")!.body).toMatchObject({
      storage: "Server",
      status: "submitted",
      external_url: "",
      attachment: null,
    });
  });

  it("shows a saved plan and lets a lead approve it", async () => {
    const calls = mockFetch(
      base(LEAD, saved, {
        [`POST ${D}approve/`]: { body: { ...saved, status: "approved", approved_by: user } },
      }),
    );
    open();
    const panel = await screen.findByRole("region", { name: "Data management plan" });
    expect(await within(panel).findByText("Draft")).toBeInTheDocument();
    await userEvent.click(within(panel).getByText("Storage and backup"));
    expect(within(panel).getByText("Encrypted lab server")).toBeVisible();
    await userEvent.click(within(panel).getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
  });

  it("warns that editing an approved plan reopens it, and hides Approve", async () => {
    mockFetch(base(LEAD, { ...saved, status: "approved", approved_by: user }));
    open();
    expect(await screen.findByText("Approved")).toBeInTheDocument();
    expect(screen.getByText(/Approved by Ada/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Edit plan" }));
    expect(screen.getByRole("note")).toHaveTextContent(/back to draft/);
  });

  it("gives contributors Edit but not Approve or Delete, and viewers neither", async () => {
    mockFetch(base(CONTRIB, saved));
    open();
    expect(await screen.findByRole("button", { name: "Edit plan" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete plan" })).not.toBeInTheDocument();
  });

  it("is read-only for a viewer", async () => {
    mockFetch(base(VIEWER, saved));
    open();
    await screen.findByRole("region", { name: "Data management plan" });
    await screen.findByText("Draft");
    expect(
      screen.queryByRole("button", { name: /Edit plan|Start plan|Approve/ }),
    ).not.toBeInTheDocument();
  });

  it("lists the version history", async () => {
    mockFetch(
      base(LEAD, saved, {
        [`GET ${D}revisions/`]: {
          body: [
            {
              id: "v2",
              number: 2,
              snapshot: { status: "submitted" },
              created_by: user,
              created_at: "2026-05-02T10:00:00Z",
            },
            {
              id: "v1",
              number: 1,
              snapshot: { status: "draft" },
              created_by: user,
              created_at: "2026-05-01T10:00:00Z",
            },
          ],
        },
      }),
    );
    open();
    await userEvent.click(await screen.findByRole("button", { name: "History" }));
    const history = await screen.findByLabelText("Plan history");
    expect(await within(history).findByText("Version 2")).toBeInTheDocument();
    expect(within(history).getByText("Version 1")).toBeInTheDocument();
  });

  it("asks before deleting", async () => {
    const calls = mockFetch(base(LEAD, saved, { [`DELETE ${D}`]: { status: 204, body: null } }));
    open();
    await userEvent.click(await screen.findByRole("button", { name: "Delete plan" }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });
});
