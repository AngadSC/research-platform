import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const L = "/api/labs/lab1";
const P = `${L}/projects/p1`;
const person = (id: string, name: string, email: string) => ({ id, display_name: name, email });
const ada = person("u1", "Ada Example", "ada@uni.edu");
const lee = person("u2", "Lee Lead", "lee@uni.edu");
const msg = (
  id: string,
  author: typeof ada,
  body: string,
  created_at = "2030-01-02T10:00:00Z",
) => ({
  id,
  author,
  body,
  created_at,
});

const project = (perms: string[]) => ({
  id: "p1",
  name: "Sleep",
  status: "active",
  description: "",
  my_permissions: ["view_project", ...perms],
});

function world(messages: unknown[], perms: string[] = []) {
  const p = project(perms);
  return {
    [SESSION]: signedIn,
    "GET /api/labs/": { body: [makeLab(["view_lab"])] },
    [`GET ${L}/`]: { body: makeLab(["view_lab"]) },
    [`GET ${L}/projects/`]: { body: [p] },
    [`GET ${P}/`]: { body: p },
    [`GET ${P}/documents/`]: { body: [] },
    [`GET ${P}/datasets/`]: { body: [] },
    [`GET ${P}/analyses/`]: { body: [] },
    [`GET ${P}/results/`]: { body: [] },
    [`GET ${P}/decisions/`]: { body: [] },
    [`GET ${P}/manuscripts/`]: { body: [] },
    [`GET ${L}/notifications/`]: { body: [] },
    [`GET ${P}/messages/`]: { body: messages },
    [`POST ${P}/messages/read/`]: { status: 204 },
    [`GET ${L}/chat/unread/`]: { body: [] },
  };
}

describe("project chat", () => {
  it("shows the conversation and the participant-data notice", async () => {
    mockFetch(world([msg("1", lee, "Morning all"), msg("2", ada, "Hi Lee")]));
    renderRoute("/labs/lab1/projects/p1/chat");
    const log = await screen.findByRole("log", { name: "Messages" });
    expect(await within(log).findByText("Morning all")).toBeInTheDocument();
    expect(within(log).getByText("Lee Lead")).toBeInTheDocument();
    expect(within(log).getByText("You")).toBeInTheDocument();
    expect(screen.getByText(/Do not share participant identifiers/)).toBeInTheDocument();
  });

  it("sends on Enter and clears the box; Shift+Enter makes a new line", async () => {
    const calls = mockFetch({
      ...world([]),
      [`POST ${P}/messages/`]: { status: 201, body: msg("3", ada, "one\ntwo") },
    });
    renderRoute("/labs/lab1/projects/p1/chat");
    expect(await screen.findByText("No messages yet")).toBeInTheDocument();
    const box = screen.getByLabelText("Message");
    await userEvent.type(box, "one{Shift>}{Enter}{/Shift}two{Enter}");
    await waitFor(() => expect(box).toHaveValue(""));
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ body: "one\ntwo" });
  });

  it("keeps the draft when sending fails", async () => {
    const calls = mockFetch({
      ...world([]),
      [`POST ${P}/messages/`]: { status: 429, body: { detail: "Too many." } },
    });
    renderRoute("/labs/lab1/projects/p1/chat");
    const box = await screen.findByLabelText("Message");
    await userEvent.type(box, "keep me{Enter}");
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    await waitFor(() => expect(screen.getByRole("button", { name: "Send" })).toBeEnabled());
    expect(box).toHaveValue("keep me");
  });

  it("does not send a blank message", async () => {
    const calls = mockFetch(world([]));
    renderRoute("/labs/lab1/projects/p1/chat");
    const box = await screen.findByLabelText("Message");
    await userEvent.type(box, "   {Enter}");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("lets you delete your own message but not someone else's", async () => {
    const calls = mockFetch({
      ...world([msg("1", lee, "theirs"), msg("2", ada, "mine")]),
      [`DELETE ${L}/messages/2/`]: { status: 204 },
    });
    renderRoute("/labs/lab1/projects/p1/chat");
    await screen.findByText("theirs");
    expect(screen.queryByRole("button", { name: /Delete message: theirs/ })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /Delete message: mine/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Delete message" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("lets a project lead delete anyone's message", async () => {
    mockFetch(world([msg("1", lee, "theirs")], ["edit_project"]));
    renderRoute("/labs/lab1/projects/p1/chat");
    expect(
      await screen.findByRole("button", { name: /Delete message: theirs/ }),
    ).toBeInTheDocument();
  });

  it("offers earlier messages only when a full page came back, then loads them", async () => {
    const page = Array.from({ length: 100 }, (_, i) =>
      msg(`m${i}`, lee, `message ${i}`, `2030-01-02T10:${String(i % 60).padStart(2, "0")}:00Z`),
    );
    const before = encodeURIComponent(page[0]!.created_at);
    mockFetch({
      ...world(page),
      [`GET ${P}/messages/?before=${before}`]: { body: [msg("old", lee, "the very first")] },
    });
    renderRoute("/labs/lab1/projects/p1/chat");
    await userEvent.click(await screen.findByRole("button", { name: "Load earlier messages" }));
    expect(await screen.findByText("the very first")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load earlier messages" })).toBeNull();
  });
});

describe("read state", () => {
  it("marks the chat read up to the newest message on screen", async () => {
    const calls = mockFetch(
      world([msg("1", lee, "one"), msg("2", lee, "two", "2030-01-02T11:30:00.123456Z")]),
    );
    renderRoute("/labs/lab1/projects/p1/chat");
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith("/messages/read/"))?.body).toEqual({
        last_read_at: "2030-01-02T11:30:00.123456Z",
      }),
    );
  });

  it("does not mark an empty chat read", async () => {
    const calls = mockFetch(world([]));
    renderRoute("/labs/lab1/projects/p1/chat");
    await screen.findByText("No messages yet");
    expect(calls.some((c) => c.path.endsWith("/messages/read/"))).toBe(false);
  });

  it("shows the unread count on the project when collapsed and on Chat when open", async () => {
    mockFetch({
      ...world([]),
      [`GET ${L}/chat/unread/`]: { body: [{ project: "p1", count: 3 }] },
    });
    renderRoute("/labs/lab1/projects/p1/tasks");
    const nav = within(await screen.findByRole("navigation", { name: "Projects" }));
    expect(await nav.findByRole("link", { name: /Chat.*3 unread messages/ })).toBeInTheDocument();
    await userEvent.click(nav.getByRole("button", { name: "Sleep sections" }));
    expect(nav.getByRole("link", { name: /Sleep.*3 unread messages/ })).toBeInTheDocument();
  });

  it("caps a large count at 99+", async () => {
    mockFetch({
      ...world([]),
      [`GET ${L}/chat/unread/`]: { body: [{ project: "p1", count: 240 }] },
    });
    renderRoute("/labs/lab1/projects/p1/tasks");
    expect((await screen.findAllByText("99+")).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("img", { name: "240 unread messages" }).length).toBeGreaterThan(0);
  });
});

describe("project sidebar dropdown", () => {
  it("opens the current project's sections, chat included, and can collapse", async () => {
    mockFetch(world([]));
    renderRoute("/labs/lab1/projects/p1/chat");
    const nav = within(await screen.findByRole("navigation", { name: "Projects" }));
    const toggle = await nav.findByRole("button", { name: "Sleep sections" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    for (const name of ["Overview", "Tasks", "Documents", "Files", "Workflow", "Lineage"])
      expect(nav.getByRole("link", { name })).toBeInTheDocument();
    expect(nav.getByRole("link", { name: "Chat" })).toHaveAttribute(
      "href",
      "/labs/lab1/projects/p1/chat",
    );
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(nav.queryByRole("link", { name: "Chat" })).toBeNull();
  });
});
