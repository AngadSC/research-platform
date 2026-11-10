import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const L = "/api/labs/lab1";
const P = "/labs/lab1/projects/p1";
const project = {
  id: "p1",
  name: "Sleep",
  color: "teal",
  status: "active",
  my_permissions: ["view_project"],
};

function world(preferences: object) {
  const me = { id: "u1", email: "ada@uni.edu", display_name: "Ada Byron", preferences };
  return {
    [SESSION]: signedIn,
    "GET /api/me/": { body: me },
    "PATCH /api/me/": (req: { body: unknown }) => ({
      body: { ...me, preferences: (req.body as { preferences: object }).preferences },
    }),
    "GET /api/labs/": { body: [makeLab(["view_lab"])] },
    [`GET ${L}/`]: { body: makeLab(["view_lab"]) },
    [`GET ${L}/projects/`]: { body: [project] },
    [`GET ${L}/projects/p1/`]: { body: project },
    [`GET ${L}/chat/unread/`]: { body: [] },
    [`GET ${L}/notifications/`]: { body: [] },
  };
}

const patches = (calls: ReturnType<typeof mockFetch>) =>
  calls.filter((c) => c.method === "PATCH").map((c) => c.body);

describe("app shell", () => {
  beforeEach(() => localStorage.clear());

  it("records the project once its name has loaded", async () => {
    const calls = mockFetch(world({}));
    renderRoute(`${P}/overview`);
    await waitFor(() => expect(patches(calls)).toHaveLength(1));
    expect(patches(calls)[0]).toMatchObject({
      preferences: { recents: [{ url: P, label: "Sleep", kind: "project" }] },
    });
  });

  it("does not save when the project is already the top recent", async () => {
    const top = { url: P, label: "Sleep", kind: "project", at: "2026-11-08T12:00:00.000Z" };
    const calls = mockFetch(world({ recents: [top] }));
    renderRoute(`${P}/overview`);
    await screen.findByRole("button", { name: "Sleep sections" });
    expect(patches(calls)).toEqual([]);
  });

  it("pins the page from the header and unpins it from the sidebar", async () => {
    const calls = mockFetch(world({}));
    renderRoute("/labs/lab1/members");
    await userEvent.click(await screen.findByRole("button", { name: "Pin this page" }));
    expect(patches(calls)).toContainEqual({
      preferences: { pins: [{ url: "/labs/lab1/members", label: "Members" }] },
    });
    const pinned = within(await screen.findByRole("navigation", { name: "Pinned" }));
    expect(pinned.getByRole("link", { name: "Members" })).toHaveAttribute(
      "href",
      "/labs/lab1/members",
    );
    await userEvent.click(pinned.getByRole("button", { name: "Unpin Members" }));
    expect(screen.queryByRole("navigation", { name: "Pinned" })).toBeNull();
    expect(patches(calls)).toContainEqual({ preferences: { pins: [] } });
  });

  it("will not link a saved address off this site", async () => {
    mockFetch(
      world({
        pins: [
          { url: "//evil.example", label: "Evil" },
          { url: "/labs/lab1/members", label: "Team" },
        ],
      }),
    );
    renderRoute("/labs/lab1/members");
    const pinned = within(await screen.findByRole("navigation", { name: "Pinned" }));
    expect(pinned.getByRole("link", { name: "Team" })).toBeInTheDocument();
    expect(pinned.queryByRole("link", { name: "Evil" })).toBeNull();
  });

  it("hides the sidebar and remembers that", async () => {
    mockFetch(world({}));
    renderRoute("/labs/lab1/members");
    await userEvent.click(await screen.findByRole("button", { name: "Hide sidebar" }));
    expect(screen.getByRole("button", { name: "Show sidebar" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(localStorage.getItem("sidebar-hidden")).toBe("1");
  });

  it("keeps the current lab in the sidebar on Settings, and has no theme control in the header", async () => {
    localStorage.setItem("last-lab", "lab2");
    const lab2 = { ...makeLab(["view_lab"]), id: "lab2", name: "Second Lab" };
    mockFetch({ ...world({}), "GET /api/labs/": { body: [makeLab(["view_lab"]), lab2] } });
    renderRoute("/settings");
    await screen.findByRole("heading", { name: "Appearance" });
    const main = within(await screen.findByRole("navigation", { name: "Main" }));
    expect(await main.findByRole("link", { name: "Members" })).toHaveAttribute(
      "href",
      "/labs/lab2/members",
    );
    expect(screen.getByRole("button", { name: "Switch lab" })).toHaveTextContent("Second Lab");
    expect(within(screen.getAllByRole("banner")[0]!).queryByRole("radio")).toBeNull();
  });

  it("forgets a remembered lab you no longer belong to", async () => {
    localStorage.setItem("last-lab", "gone");
    mockFetch(world({}));
    renderRoute("/settings");
    expect(await screen.findByRole("link", { name: "Members" })).toHaveAttribute(
      "href",
      "/labs/lab1/members",
    );
  });

  it("sends Home to the lab's own page, not the dashboard", async () => {
    mockFetch(world({}));
    const router = renderRoute("/labs/lab1/members");
    const main = within(await screen.findByRole("navigation", { name: "Main" }));
    await userEvent.click(await main.findByRole("link", { name: "Home" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/labs/lab1/projects"));
  });

  it("adds a lab from the sidebar", async () => {
    mockFetch(world({}));
    const router = renderRoute("/labs/lab1/members");
    await userEvent.click(await screen.findByRole("button", { name: "Create a lab" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/labs/new"));
  });

  it("goes to the signed-out home page after signing out", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    mockFetch({
      ...world({}),
      "DELETE /_allauth/browser/v1/auth/session": { status: 401, body: { status: 401 } },
    });
    renderRoute("/labs/lab1/members");
    await userEvent.click(await screen.findByRole("button", { name: "Account menu" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Sign out" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("/"));
  });

  it("shows a placeholder bar, not the word Lab, until the lab has loaded", async () => {
    mockFetch(world({}));
    const answer = vi.mocked(fetch).getMockImplementation()!;
    vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) =>
      String(input) === "/api/labs/" ? new Promise(() => {}) : answer(input, init),
    );
    renderRoute("/labs/lab1/members");
    const crumbs = within(await screen.findByRole("navigation", { name: "Breadcrumb" }));
    expect(crumbs.getByLabelText("Loading")).toBeInTheDocument();
    expect(crumbs.queryByText("Lab")).toBeNull();
  });

  it("moves Settings and Sign out into the account menu", async () => {
    mockFetch(world({}));
    const router = renderRoute("/labs/lab1/members");
    const trigger = await screen.findByRole("button", { name: "Account menu" });
    await within(trigger).findByText("Ada Byron");
    expect(screen.queryByRole("button", { name: "Sign out" })).toBeNull();
    expect(
      within(screen.getByRole("navigation", { name: "Main" })).queryByRole("link", {
        name: "Settings",
      }),
    ).toBeNull();
    await userEvent.click(trigger);
    expect(await screen.findByRole("menuitem", { name: "Sign out" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("menuitem", { name: "Security" }));
    await waitFor(() => expect(router.state.location.hash).toBe("#security"));
  });
});
