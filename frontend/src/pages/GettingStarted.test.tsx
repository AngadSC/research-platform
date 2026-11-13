import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const L = "/api/labs/lab1";
const me = { id: "u1", email: "ada@uni.edu", preferences: {} };
const shell = (perms: string[], extra: Record<string, unknown> = {}) => ({
  [SESSION]: signedIn,
  "GET /api/me/": { body: me },
  "GET /api/labs/": { body: [makeLab(perms)] },
  [`GET ${L}/`]: { body: makeLab(perms) },
  [`GET ${L}/projects/`]: { body: [] },
  [`GET ${L}/chat/unread/`]: { body: [] },
  [`GET ${L}/notifications/`]: { body: [] },
  ...extra,
});
const steps = [
  { key: "members", done: true, can_act: true },
  { key: "project", done: false, can_act: true },
  { key: "training", done: false, can_act: false },
];

beforeEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("getting started", () => {
  const home = (body: unknown, extra: Record<string, unknown> = {}) =>
    shell(["view_lab"], {
      [`GET ${L}/my-tasks/`]: { body: [] },
      [`GET ${L}/getting-started/`]: { body },
      ...extra,
    });

  it("links only the steps this person can do", async () => {
    mockFetch(home({ steps, dismissed: false }));
    renderRoute("/labs/lab1/dashboard");
    const card = await screen.findByRole("region", { name: "Get your lab set up" });
    expect(within(card).getByText("1 of 3 done. These tick themselves as you go.")).toBeVisible();
    expect(within(card).getByRole("link", { name: "New project" })).toHaveAttribute(
      "href",
      "/labs/lab1/projects?new=project",
    );
    expect(within(card).queryByRole("link", { name: "Open Training" })).toBeNull();
    expect(within(card).getByText("Your PI or lab admin can do this.")).toBeVisible();
  });

  it("goes away when dismissed", async () => {
    const calls = mockFetch(
      home(
        { steps, dismissed: false },
        { [`POST ${L}/getting-started/`]: { body: { steps, dismissed: true } } },
      ),
    );
    renderRoute("/labs/lab1/dashboard");
    await userEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "Get your lab set up" })).toBeNull(),
    );
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ dismissed: true });
  });

  it("leaves a way back once dismissed", async () => {
    const calls = mockFetch(
      home(
        { steps, dismissed: true },
        { [`POST ${L}/getting-started/`]: { body: { steps, dismissed: false } } },
      ),
    );
    renderRoute("/labs/lab1/dashboard");
    await userEvent.click(await screen.findByRole("button", { name: "Show getting started" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({ dismissed: false }),
    );
    expect(await screen.findByRole("region", { name: "Get your lab set up" })).toBeVisible();
  });

  it("is hidden once every step is done", async () => {
    mockFetch(home({ steps: [{ key: "project", done: true, can_act: true }], dismissed: false }));
    renderRoute("/labs/lab1/dashboard");
    await screen.findByRole("heading", { name: "My tasks" });
    expect(screen.queryByRole("region", { name: "Get your lab set up" })).toBeNull();
  });
});

describe("tutorial and help", () => {
  const help = () =>
    shell(["view_lab"], {
      [`GET ${L}/getting-started/`]: { body: { steps, dismissed: true } },
      [`GET ${L}/my-tasks/`]: { body: [] },
    });

  it("walks through the steps, opens each page and can be closed", async () => {
    mockFetch(help());
    const router = renderRoute("/labs/lab1/calendar");
    await userEvent.click(await screen.findByRole("button", { name: "Account menu" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: /Help/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Take the tour" }));
    const tour = await screen.findByRole("dialog", { name: "Tutorial" });
    expect(within(tour).getByText("Step 1 of 9")).toBeVisible();
    expect(router.state.location.pathname).toBe("/labs/lab1/dashboard");
    await userEvent.click(within(tour).getByRole("button", { name: "Next" }));
    expect(within(tour).getByText("Step 2 of 9")).toBeVisible();
    expect(router.state.location.pathname).toBe("/labs/lab1/projects");
    await userEvent.click(within(tour).getByRole("button", { name: "Close tutorial" }));
    expect(screen.queryByRole("dialog", { name: "Tutorial" })).toBeNull();
    expect(localStorage.getItem("tutorial-step")).toBeNull();
  });

  it("offers the dismissed checklist again and lists shortcuts", async () => {
    const calls = mockFetch({
      ...help(),
      [`POST ${L}/getting-started/`]: { body: { steps, dismissed: false } },
    });
    renderRoute("/help");
    expect(await screen.findByText("Save the document you are editing")).toBeVisible();
    await userEvent.click(
      await screen.findByRole("button", { name: "Show the getting-started checklist" }),
    );
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({ dismissed: false }),
    );
  });
});

describe("lab documents", () => {
  const doc = {
    id: "d1",
    project: null,
    folder: null,
    title: "Lab manual",
    embed_url: "",
    embed_open_url: "",
    version: 1,
    content: [],
    updated_by: { id: "u1", email: "ada@uni.edu", display_name: "Ada" },
    retain_until: null,
    retention_note: "",
    created_at: "2026-11-01T10:00:00Z",
    updated_at: "2026-11-01T10:00:00Z",
  };

  it("hides New document from people who cannot add", async () => {
    mockFetch(shell(["view_lab"], { [`GET ${L}/lab-documents/`]: { body: [doc] } }));
    renderRoute("/labs/lab1/documents");
    expect(await screen.findByText("Lab manual")).toBeVisible();
    expect(screen.queryByRole("button", { name: "New document" })).toBeNull();
  });

  it("creates through the lab-wide route and opens the document", async () => {
    const calls = mockFetch(
      shell(["view_lab", "contribute_lab"], {
        [`GET ${L}/lab-documents/`]: { body: [] },
        [`POST ${L}/lab-documents/`]: { status: 201, body: doc },
        [`GET ${L}/documents/d1/`]: { body: doc },
      }),
    );
    const router = renderRoute("/labs/lab1/documents");
    await userEvent.click((await screen.findAllByRole("button", { name: "New document" }))[0]!);
    await userEvent.type(await screen.findByLabelText("Title"), "Lab manual");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/labs/lab1/documents/d1"));
    expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({ title: "Lab manual" });
  });
});

describe("project templates", () => {
  it("sends the chosen template with a new project", async () => {
    const calls = mockFetch(
      shell(["view_lab", "create_project"], {
        [`POST ${L}/projects/`]: { status: 201, body: { id: "p1", name: "Thesis" } },
        [`GET ${L}/projects/p1/`]: { status: 404, body: {} },
      }),
    );
    renderRoute("/labs/lab1/projects?new=project");
    await userEvent.type(await screen.findByLabelText("Name"), "Thesis");
    await userEvent.click(screen.getByRole("combobox", { name: "Start from" }));
    await userEvent.click(await screen.findByRole("option", { name: /Honours thesis/ }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST" && c.path.endsWith("/projects/"))?.body).toEqual(
        expect.objectContaining({ name: "Thesis", template: "honours_thesis" }),
      ),
    );
  });
});
