import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const me = { id: "u1", email: "ada@uni.edu", display_name: "Ada", preferences: {} };
const base = (perms: string[]) => ({
  [SESSION]: signedIn,
  "GET /api/me/": { body: me },
  "GET /api/labs/": { body: [makeLab(perms)] },
  "GET /api/ai/grants/": { body: [] },
  "PATCH /api/me/": (req: { body: unknown }) => ({
    body: { ...me, preferences: (req.body as { preferences: object }).preferences },
  }),
});

describe("settings", () => {
  beforeEach(() => localStorage.clear());

  it("splits its sections into tabs, opening the one in the address", async () => {
    mockFetch(base(["view_lab"]));
    renderRoute("/settings");
    expect(await screen.findByLabelText("Name")).toHaveValue("Ada");
    expect(screen.queryByRole("heading", { name: "Appearance" })).toBeNull();
    const tabs = screen.getByRole("navigation", { name: "Settings sections" });
    for (const name of ["Profile", "Appearance", "Notifications", "Security", "AI"])
      expect(within(tabs).getByRole("link", { name })).toBeInTheDocument();
    await userEvent.click(within(tabs).getByRole("link", { name: "Notifications" }));
    expect(await screen.findByRole("list", { name: "Emailed notifications" })).toHaveTextContent(
      "Ethics approval expiring",
    );
    expect(within(tabs).getByRole("link", { name: "Notifications" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.queryByLabelText("Name")).toBeNull();
  });

  it("saves a readable custom theme and applies it, and refuses an unreadable one", async () => {
    const calls = mockFetch({
      ...base(["view_lab"]),
      "PATCH /api/me/": (req: { body: unknown }) => ({
        body: { ...me, preferences: (req.body as { preferences: object }).preferences },
      }),
    });
    renderRoute("/settings#appearance");
    const form = await screen.findByRole("form", { name: "Make a colour theme" });
    await userEvent.type(within(form).getByLabelText("Theme name"), "Night");
    const save = within(form).getByRole("button", { name: "Save and use" });
    fireEvent.input(within(form).getByLabelText("Text"), { target: { value: "#cccccc" } });
    expect(within(form).getByRole("alert")).toHaveTextContent(/too hard to read/);
    expect(save).toBeDisabled();
    fireEvent.input(within(form).getByLabelText("Background"), { target: { value: "#101020" } });
    fireEvent.input(within(form).getByLabelText("Text"), { target: { value: "#f0f0f0" } });
    fireEvent.input(within(form).getByLabelText("Accent"), { target: { value: "#ffcc00" } });
    await waitFor(() => expect(save).toBeEnabled());
    await userEvent.click(save);
    await waitFor(() =>
      expect(document.documentElement.style.getPropertyValue("--background")).toBe("#101020"),
    );
    const body = calls.find((c) => c.method === "PATCH")?.body as {
      preferences: { theme: string; custom_themes: { id: string; name: string }[] };
    };
    expect(body.preferences.custom_themes[0]).toMatchObject({ name: "Night", accent: "#ffcc00" });
    expect(body.preferences.theme).toBe(`custom:${body.preferences.custom_themes[0]!.id}`);
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    await userEvent.click(await screen.findByRole("radio", { name: "Light" }));
    expect(document.documentElement.style.getPropertyValue("--background")).toBe("");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("saves the theme and the default task view to the account", async () => {
    const calls = mockFetch(base(["view_lab"]));
    renderRoute("/settings#appearance");
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
    expect(await screen.findByRole("link", { name: "Open Lab details" })).toHaveAttribute(
      "href",
      "/labs/lab1/admin",
    );
  });

  it("does not offer Admin to a member", async () => {
    mockFetch(base(["view_lab"]));
    renderRoute("/settings");
    await screen.findByRole("link", { name: "Open integrations" });
    expect(screen.queryByRole("link", { name: "Open Lab details" })).not.toBeInTheDocument();
  });

  it("shows the two-step setup key only after asking to set it up", async () => {
    mockFetch({
      ...base(["view_lab"]),
      "GET /_allauth/browser/v1/account/authenticators/totp": {
        status: 404,
        body: { status: 404, meta: { secret: "FAKESECRET" } },
      },
    });
    renderRoute("/settings#security");
    const start = await screen.findByRole("button", { name: "Set up two-step verification" });
    expect(screen.queryByText("FAKESECRET")).not.toBeInTheDocument();
    await userEvent.click(start);
    expect(await screen.findByText("FAKESECRET")).toBeInTheDocument();
  });

  it("keeps the old /account address working", async () => {
    mockFetch(base(["view_lab"]));
    const router = renderRoute("/account");
    expect(await screen.findByRole("heading", { name: "Security" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/settings");
  });
});
