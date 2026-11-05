import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const ADMIN = ["view_lab", "manage_lab", "manage_inventory", "view_audit_log", "view_ethics"];
const lab = (perms: string[]) => ({
  ...makeLab(perms),
  department: "",
  description: "",
  address: "",
  contact_email: "",
  website: "",
});
const base = (perms: string[], extra: Record<string, unknown> = {}) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [lab(perms)] },
  "GET /api/labs/lab1/": { body: lab(perms) },
  "GET /api/labs/lab1/members/": {
    body: [
      {
        id: "m1",
        role: "member",
        created_at: "2026-01-01T00:00:00Z",
        user: { id: "u2", email: "bob@uni.edu", display_name: "Bob" },
      },
    ],
  },
  "GET /api/labs/lab1/onboarding-items/": { body: [] },
  "GET /api/labs/lab1/inventory/?ordering=name": { body: [] },
  "GET /api/labs/lab1/institution-resources/": { body: [] },
  ...extra,
});

describe("admin area", () => {
  it("shows every section and the tool links to an admin", async () => {
    mockFetch(base(ADMIN));
    renderRoute("/labs/lab1/admin");
    expect(await screen.findByRole("heading", { name: "Lab details" })).toBeInTheDocument();
    for (const name of ["Turnover and onboarding", "Inventory", "Institution resources"])
      expect(screen.getByRole("heading", { name })).toBeInTheDocument();
    const tools = screen.getByRole("region", { name: "Admin tools" });
    for (const name of [
      "Ethics approvals",
      "Audit log",
      "Retention review",
      "Members",
      "Integrations",
    ])
      expect(within(tools).getByRole("link", { name: new RegExp(name) })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Admin" }).length).toBeGreaterThan(0);
  });

  it("hides the Admin entry and explains for a member", async () => {
    mockFetch(base(["view_lab", "manage_inventory"]));
    renderRoute("/labs/lab1/admin");
    expect(await screen.findByText("You don't have access to Admin")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
  });

  it("saves lab details including the institution", async () => {
    const calls = mockFetch(base(ADMIN, { "PATCH /api/labs/lab1/": { body: lab(ADMIN) } }));
    renderRoute("/labs/lab1/admin");
    const institution = await screen.findByLabelText("Institution");
    await userEvent.clear(institution);
    await userEvent.type(institution, "University of Alberta");
    await userEvent.click(screen.getByRole("button", { name: "Save details" }));
    const patch = calls.find((c) => c.method === "PATCH");
    expect(patch?.body).toMatchObject({
      institution_name: "University of Alberta",
      name: "Ada Lab",
    });
  });

  it("adds a checklist item and ticks it for a member", async () => {
    const item = {
      id: "o1",
      kind: "new_member",
      title: "Read the data policy",
      description: "",
      url: "",
      required: true,
      order: 0,
      completed_user_ids: [],
    };
    const calls = mockFetch(
      base(ADMIN, {
        "GET /api/labs/lab1/onboarding-items/": { body: [item] },
        "POST /api/labs/lab1/onboarding-items/o1/completions/": {
          body: { ...item, completed_user_ids: ["u2"] },
        },
      }),
    );
    renderRoute("/labs/lab1/admin");
    await userEvent.click(
      await screen.findByRole("checkbox", { name: "Read the data policy done" }),
    );
    expect(calls.find((c) => c.path.endsWith("/completions/"))?.body).toEqual({
      user: "u2",
      done: true,
    });
    expect(screen.getByRole("link", { name: /Handover report for Bob/ })).toBeInTheDocument();
  });

  it("lets a member edit inventory but a viewer only read it", async () => {
    const row = {
      id: "i1",
      name: "Centrifuge",
      category: "equipment",
      location: "B12",
      quantity: "2.00",
      unit: "",
      owner: null,
      serial_number: "",
      purchase_date: null,
      due_date: null,
      status: "active",
      notes: "",
    };
    mockFetch(
      base(["view_lab", "manage_inventory"], {
        "GET /api/labs/lab1/inventory/?ordering=name": { body: [row] },
      }),
    );
    renderRoute("/labs/lab1/inventory");
    expect(await screen.findByText("Centrifuge")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add item" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Export CSV" })).toHaveAttribute(
      "href",
      "/api/labs/lab1/inventory/export/?ordering=name",
    );
  });

  it("hides inventory editing from a viewer", async () => {
    mockFetch(base(["view_lab"], { "GET /api/labs/lab1/inventory/?ordering=name": { body: [] } }));
    renderRoute("/labs/lab1/inventory");
    expect(await screen.findByText("Read only for your role.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add item" })).not.toBeInTheDocument();
  });
});

describe("institution resources editor", () => {
  const res = {
    id: "r1",
    category: "ethics",
    title: "Research Ethics Office",
    url: "https://example.edu/ethics",
    description: "",
    order: 0,
  };

  it("rejects a non-https address without calling the server", async () => {
    const calls = mockFetch(base(ADMIN));
    renderRoute("/labs/lab1/admin");
    const form = await screen.findByRole("form", { name: "Add a link" });
    await userEvent.type(within(form).getByLabelText("Link title"), "Grants");
    await userEvent.type(within(form).getByLabelText("Link address"), "http://example.edu/g");
    await userEvent.click(within(form).getByRole("button", { name: "Add link" }));
    expect(await within(form).findByText(/starting with https/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("adds and removes a link", async () => {
    const calls = mockFetch(
      base(ADMIN, {
        "GET /api/labs/lab1/institution-resources/": { body: [res] },
        "POST /api/labs/lab1/institution-resources/": { status: 201, body: res },
        "DELETE /api/labs/lab1/institution-resources/r1/": { status: 204 },
      }),
    );
    renderRoute("/labs/lab1/admin");
    expect(await screen.findByRole("link", { name: "Research Ethics Office" })).toBeInTheDocument();
    const form = screen.getByRole("form", { name: "Add a link" });
    await userEvent.type(within(form).getByLabelText("Link title"), "Grants");
    await userEvent.type(within(form).getByLabelText("Link address"), "https://example.edu/g");
    await userEvent.click(within(form).getByRole("button", { name: "Add link" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove Research Ethics Office" }));
    const post = calls.find((c) => c.method === "POST");
    expect(post?.body).toMatchObject({
      category: "ethics",
      title: "Grants",
      url: "https://example.edu/g",
    });
    expect(calls.some((c) => c.method === "DELETE")).toBe(true);
  });
});
