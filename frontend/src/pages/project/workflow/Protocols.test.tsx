import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const user = { id: "u1", email: "ada@uni.edu", display_name: "Ada" };
const P = "/api/labs/lab1/projects/p1";
const W = "/labs/lab1/projects/p1/workflow";
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
const reagent = {
  id: "r1",
  item: "i1",
  item_name: "Ethanol",
  amount: "2.00",
  unit: "mL",
  stock: "10.00",
  stock_unit: "mL",
};
const protocol = { id: "pr1", name: "PCR", notes: "", reagents: [reagent], created_at: "" };

const base = (perms: string[], extra: Record<string, unknown> = {}) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(["view_lab"])] },
  "GET /api/labs/lab1/": { body: makeLab(["view_lab"]) },
  "GET /api/labs/lab1/projects/": { body: [project(perms)] },
  [`GET ${P}/`]: { body: project(perms) },
  [`GET ${P}/workflow-progress/`]: { body: { stages: [], next: "ethics" } },
  [`GET ${P}/protocols/`]: { body: [protocol] },
  [`GET ${P}/inventory-usage/`]: { body: [] },
  ...extra,
});

describe("Protocols", () => {
  it("records a use with the amount typed and shows the server's message on failure", async () => {
    const calls = mockFetch(
      base(["view_project", "edit_content"], {
        "POST /api/labs/lab1/protocols/pr1/use/": {
          status: 400,
          body: { amount: "Only 1 mL of Ethanol is left, so 5 mL cannot be taken." },
        },
      }),
    );
    renderRoute(`${W}/protocols`);
    await userEvent.click(await screen.findByRole("button", { name: "Used Ethanol" }));
    const amount = await screen.findByLabelText("Amount used (mL)");
    await userEvent.clear(amount);
    await userEvent.type(amount, "5");
    await userEvent.click(screen.getByRole("button", { name: "Take out of stock" }));
    expect(await screen.findByText(/Only 1 mL of Ethanol is left/)).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.body).toMatchObject({ reagent: "r1", amount: "5" });
    expect(typeof (post.body as { request_id: string }).request_id).toBe("string");
  });

  it("asks before deleting a protocol", async () => {
    const calls = mockFetch(
      base(["view_project", "edit_content"], {
        "DELETE /api/labs/lab1/protocols/pr1/": { status: 204 },
      }),
    );
    renderRoute(`${W}/protocols`);
    await userEvent.click(await screen.findByRole("button", { name: "Delete PCR" }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Delete protocol" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("hides recording from someone who can only view the project", async () => {
    mockFetch(base(["view_project"]));
    renderRoute(`${W}/protocols`);
    await waitFor(() => expect(screen.getByText("PCR")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Used Ethanol" })).toBeNull();
  });
});
