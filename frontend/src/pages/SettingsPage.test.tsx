import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const me = { id: "u1", email: "ada@uni.edu", display_name: "Ada", preferences: {} };
const base = (perms: string[]) => ({
  [SESSION]: signedIn,
  "GET /api/me/": { body: me },
  "GET /api/labs/": { body: [makeLab(perms)] },
  "PATCH /api/me/": (req: { body: unknown }) => ({
    body: { ...me, preferences: (req.body as { preferences: object }).preferences },
  }),
});

describe("settings", () => {
  beforeEach(() => localStorage.clear());

  it("has every section", async () => {
    mockFetch(base(["view_lab"]));
    renderRoute("/settings");
    for (const name of ["Appearance", "Tasks", "Notifications", "Security", "Integrations"])
      expect(await screen.findByRole("heading", { name })).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveValue("Ada");
    expect(screen.getByRole("list", { name: "Emailed notifications" })).toHaveTextContent(
      "Ethics approval expiring",
    );
  });

  it("saves the theme and the default task view to the account", async () => {
    const calls = mockFetch(base(["view_lab"]));
    renderRoute("/settings");
    const appearance = await screen.findByRole("region", { name: "Appearance" });
    await userEvent.click(within(appearance).getByRole("radio", { name: "Dark" }));
    const tasks = screen.getByRole("region", { name: "Tasks" });
    await userEvent.click(within(tasks).getByRole("radio", { name: "List" }));
    const bodies = calls.filter((c) => c.method === "PATCH").map((c) => c.body);
    expect(bodies).toContainEqual({ preferences: { theme: "dark" } });
    expect(bodies).toContainEqual({ preferences: { task_view: "list" } });
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(within(tasks).getByRole("radio", { name: "List" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("links to Admin only for someone who can manage the lab", async () => {
    mockFetch(base(["view_lab", "manage_lab"]));
    renderRoute("/settings");
    expect(await screen.findByRole("link", { name: "Open Admin" })).toHaveAttribute(
      "href",
      "/labs/lab1/admin",
    );
  });

  it("does not offer Admin to a member", async () => {
    mockFetch(base(["view_lab"]));
    renderRoute("/settings");
    await screen.findByRole("link", { name: "Open integrations" });
    expect(screen.queryByRole("link", { name: "Open Admin" })).not.toBeInTheDocument();
  });

  it("keeps the old /account address working", async () => {
    mockFetch(base(["view_lab"]));
    const router = renderRoute("/account");
    expect(await screen.findByRole("heading", { name: "Appearance" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/settings");
  });
});
