import { fireEvent, waitFor, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { localDateISO } from "@/lib/format";
import { suggestedQuantity } from "@/pages/admin/OrdersSection";
import {
  makeLab,
  mockFetch,
  openSidebarGroup,
  renderRoute,
  SESSION,
  signedIn,
  pickMenuItem,
} from "@/test/utils";

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
  "GET /api/labs/lab1/inventory/orders/": { body: [] },
  "GET /api/labs/lab1/institution-resources/": { body: [] },
  "GET /api/labs/lab1/training/requirements/": { body: [] },
  "GET /api/labs/lab1/training/compliance/": {
    body: {
      requirements: [],
      members: [],
      summary: { done: 0, expiring: 0, expired: 0, missing: 0 },
    },
  },
  "GET /api/labs/lab1/projects/": { body: [] },
  ...extra,
});

describe("admin area", () => {
  it("holds only the lab's own details, and links nothing it does not own", async () => {
    mockFetch(base(ADMIN));
    renderRoute("/labs/lab1/admin");
    await screen.findByRole("heading", { name: "About this lab" });
    expect(screen.getByRole("heading", { name: "Lab details" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Institution resources" })).toBeNull();
    const tabs = screen.getByRole("navigation", { name: "Lab details sections" });
    for (const [tab, name] of [
      ["Onboarding", "Turnover and onboarding"],
      ["Links", "Institution resources"],
    ] as const) {
      await userEvent.click(within(tabs).getByRole("link", { name: tab }));
      expect(await screen.findByRole("heading", { name })).toBeInTheDocument();
    }
    for (const name of ["Inventory", "Training"])
      expect(screen.queryByRole("heading", { name })).toBeNull();
    await openSidebarGroup("Lab details");
    expect(await screen.findByRole("menuitem", { name: "Lab details" })).toBeInTheDocument();
  });

  it("hides the Admin group and explains for a member", async () => {
    mockFetch(base(["view_lab", "manage_inventory"]));
    renderRoute("/labs/lab1/admin");
    expect(await screen.findByText("You don't have access to Lab details")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Admin" })).toBeNull();
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
      training_requirement: null,
      training_requirement_name: "",
      training_done_user_ids: [],
    };
    const calls = mockFetch(
      base(ADMIN, {
        "GET /api/labs/lab1/onboarding-items/": { body: [item] },
        "POST /api/labs/lab1/onboarding-items/o1/completions/": {
          body: { ...item, completed_user_ids: ["u2"] },
        },
      }),
    );
    renderRoute("/labs/lab1/admin#onboarding");
    await userEvent.click(
      await screen.findByRole("checkbox", { name: "Read the data policy done" }),
    );
    expect(calls.find((c) => c.path.endsWith("/completions/"))?.body).toEqual({
      user: "u2",
      done: true,
    });
    expect(screen.getByRole("link", { name: /Handover for Bob/ })).toBeInTheDocument();
    // deleting an item asks first
    await userEvent.click(screen.getByRole("button", { name: "Delete Read the data policy" }));
    expect(await screen.findByText("Delete Read the data policy?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete item" })).toBeInTheDocument();
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
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

  it("does not overwrite stock when an edit leaves the quantity alone, and shows why a delete failed", async () => {
    const row = {
      id: "i1",
      name: "Ethanol",
      category: "reagent",
      location: "",
      quantity: "10.00",
      unit: "mL",
      owner: null,
      serial_number: "",
      purchase_date: null,
      due_date: null,
      status: "active",
      notes: "",
    };
    const calls = mockFetch(
      base(["view_lab", "manage_inventory"], {
        "GET /api/labs/lab1/inventory/?ordering=name": { body: [row] },
        "PATCH /api/labs/lab1/inventory/i1/": { body: row },
        "DELETE /api/labs/lab1/inventory/i1/": {
          status: 409,
          body: { detail: "Mark the item as retired instead." },
        },
      }),
    );
    renderRoute("/labs/lab1/inventory");
    await pickMenuItem("More for Ethanol", "Edit");
    await userEvent.click(await screen.findByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")!.body).not.toHaveProperty("quantity");
    await pickMenuItem("More for Ethanol", "Delete");
    expect(await screen.findByText("Mark the item as retired instead.")).toBeInTheDocument();
  });

  const stock = (name: string, quantity: string, extra: Record<string, unknown> = {}) => ({
    id: `i-${name}`,
    name,
    category: "reagent",
    location: "",
    quantity,
    unit: "mL",
    low_stock_at: "5",
    low: Number(quantity) <= 5,
    owner: null,
    serial_number: "",
    purchase_date: null,
    due_date: null,
    status: "active",
    notes: "",
    ...extra,
  });

  it("filters to items at or below their alert level", async () => {
    mockFetch(
      base(["view_lab", "manage_inventory"], {
        "GET /api/labs/lab1/inventory/?ordering=name": {
          body: [stock("Ethanol", "2"), stock("Water", "50")],
        },
      }),
    );
    renderRoute("/labs/lab1/inventory");
    expect(await screen.findByText("Water")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: "Low stock only" }));
    expect(screen.queryByText("Water")).not.toBeInTheDocument();
    expect(screen.getByText("Ethanol")).toBeInTheDocument();
  });

  it("closes the Use dialog after taking stock, and says who was told when it falls to the level", async () => {
    const calls = mockFetch(
      base(["view_lab", "manage_inventory"], {
        "GET /api/labs/lab1/inventory/?ordering=name": { body: [stock("Ethanol", "8")] },
        "GET /api/labs/lab1/inventory/i-Ethanol/usage/": { body: [] },
        "GET /api/labs/lab1/projects/": { body: [] },
        "POST /api/labs/lab1/inventory/i-Ethanol/usage/": { status: 201, body: {} },
      }),
    );
    renderRoute("/labs/lab1/inventory");
    await userEvent.click(await screen.findByRole("button", { name: "Use Ethanol" }));
    await userEvent.type(await screen.findByLabelText("Amount used"), "4");
    await userEvent.click(screen.getByRole("button", { name: /Take from stock/ }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(
      await screen.findByText(
        "Now at or below the alert level. PIs, lab admins and the item's owner were notified.",
      ),
    ).toBeInTheDocument();
  });

  it("lists the CSV columns and links a template", async () => {
    mockFetch(base(["view_lab", "manage_inventory"]));
    renderRoute("/labs/lab1/inventory");
    await userEvent.click(await screen.findByRole("button", { name: "Import CSV" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/low_stock_at/)).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Download template" })).toHaveAttribute(
      "href",
      "/inventory-template.csv",
    );
  });

  it("suggests a reorder quantity from the alert level, at least 1", () => {
    const item = (q: string, low: string | null) => ({ quantity: q, low_stock_at: low }) as never;
    expect(suggestedQuantity(item("3", "10"), undefined)).toBe(17);
    expect(suggestedQuantity(item("30", "10"), undefined)).toBe(1);
    expect(suggestedQuantity(item("3", null), { quantity: "4.00" } as never)).toBe(4);
    expect(suggestedQuantity(item("3", null), undefined)).toBe(1);
  });

  it("picks today's local date when a date field is double-clicked", async () => {
    mockFetch(base(["view_lab", "manage_inventory"]));
    renderRoute("/labs/lab1/inventory");
    await userEvent.click(await screen.findByRole("button", { name: "Add item" }));
    const field = await screen.findByLabelText("Purchase date");
    fireEvent.dblClick(field);
    expect(field).toHaveValue(localDateISO());
    expect(screen.getByLabelText("Calibration or maintenance due")).toHaveValue("");
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
    renderRoute("/labs/lab1/admin#links");
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
    renderRoute("/labs/lab1/admin#links");
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

  it("says when only national links are available", async () => {
    const calls = mockFetch(
      base(ADMIN, {
        "POST /api/labs/lab1/institution-resources/load-starters/": {
          body: { added: 8, institution: "Elsewhere", curated_institution: null },
        },
      }),
    );
    renderRoute("/labs/lab1/admin#links");
    await userEvent.click(await screen.findByRole("button", { name: "Get my university's forms" }));
    expect(await screen.findByText(/No curated forms for Elsewhere yet/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(true);
  });
});
