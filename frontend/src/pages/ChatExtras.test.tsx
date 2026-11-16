import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { messageLinks } from "@/components/shared/LinkCard";
import { taskText } from "@/pages/project/ChatTab";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

// Google Chat sync (D316 to D318), reactions and tasks from messages (D321), link cards (D322).

const L = "/api/labs/lab1";
const bob = { id: "u2", email: "bob@uni.edu", display_name: "Bob" };
const msg = (over: Record<string, unknown> = {}) => ({
  id: "m1",
  author: bob,
  external_author: "",
  source: "app",
  body: "Lab meeting moved",
  reactions: [],
  created_at: "2030-01-02T10:00:00Z",
  ...over,
});
const status = (over: Record<string, unknown> = {}) => ({
  bridge: null,
  configured: true,
  connected: false,
  can_manage: false,
  ...over,
});
const bridge = {
  space: "spaces/AAAA",
  space_name: "Sleep lab",
  linked_by: bob,
  last_polled_at: null,
  last_error: "",
  created_at: "2030-01-01T00:00:00Z",
};

function world(messages: unknown[], google = status(), perms = ["view_lab"]) {
  return {
    [SESSION]: signedIn,
    "GET /api/labs/": { body: [makeLab(perms)] },
    [`GET ${L}/`]: { body: makeLab(perms) },
    [`GET ${L}/projects/`]: { body: [] },
    [`GET ${L}/chat/unread/`]: { body: [] },
    [`GET ${L}/notifications/`]: { body: [] },
    [`GET ${L}/chat/messages/`]: { body: messages },
    [`POST ${L}/chat/messages/read/`]: { status: 204 },
    [`GET ${L}/chat/google/`]: { body: google },
  };
}

describe("lab chat and Google Chat", () => {
  it("shows a message from Google Chat with its sender's name", async () => {
    mockFetch(
      world([msg({ author: null, external_author: "Dana Example", source: "google_chat" })]),
    );
    renderRoute("/labs/lab1/chat");
    const log = await screen.findByRole("log", { name: "Messages" });
    expect(await within(log).findByText("Dana Example")).toBeInTheDocument();
    expect(within(log).getByText("via Google Chat")).toBeInTheDocument();
  });

  it("says where messages also go, and asks to connect to post as yourself", async () => {
    mockFetch(world([], status({ bridge })));
    renderRoute("/labs/lab1/chat");
    expect(await screen.findByText("Sleep lab")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Connect Google Chat" })).toBeInTheDocument();
    expect(
      screen.getByText(/Messages are also sent to the Google Chat Sleep lab/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Stop syncing" })).not.toBeInTheDocument();
  });

  it("lets a lab admin pick a space and start syncing", async () => {
    const calls = mockFetch({
      ...world([], status({ connected: true, can_manage: true }), [
        "view_lab",
        "manage_lab_integrations",
      ]),
      [`GET ${L}/chat/google/spaces/`]: {
        body: [{ name: "spaces/AAAA", display_name: "Sleep lab", kind: "space" }],
      },
      [`PUT ${L}/chat/google/`]: { body: status({ bridge, connected: true, can_manage: true }) },
    });
    renderRoute("/labs/lab1/chat");
    await userEvent.click(await screen.findByRole("button", { name: "Google Chat options" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Sync with Google Chat" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("combobox"));
    await userEvent.click(await screen.findByRole("option", { name: /Sleep lab/ }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Start syncing" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ space: "spaces/AAAA" }),
    );
  });
});

describe("reactions and tasks on messages", () => {
  it("shows reactions and toggles yours", async () => {
    const calls = mockFetch({
      ...world([msg({ reactions: [{ emoji: "👍", count: 2, mine: false }] })]),
      [`POST ${L}/chat/messages/m1/reactions/`]: {
        body: msg({ reactions: [{ emoji: "👍", count: 3, mine: true }] }),
      },
    });
    renderRoute("/labs/lab1/chat");
    const chip = await screen.findByRole("button", { name: /👍 2\. Add yours/ });
    await userEvent.click(chip);
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith("/reactions/"))?.body).toEqual({ emoji: "👍" }),
    );
  });

  it("reacts from the plus menu", async () => {
    const calls = mockFetch({
      ...world([msg()]),
      [`POST ${L}/chat/messages/m1/reactions/`]: { body: msg() },
    });
    renderRoute("/labs/lab1/chat");
    await userEvent.click(await screen.findByRole("button", { name: /React or make a task/ }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "React with heart" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith("/reactions/"))?.body).toEqual({
        emoji: "❤️",
      }),
    );
  });

  it("opens quick capture with the message as the task", async () => {
    mockFetch(world([msg({ body: "**Order** more agar\nby Friday" })]));
    renderRoute("/labs/lab1/chat");
    await userEvent.click(await screen.findByRole("button", { name: /React or make a task/ }));
    await userEvent.click(
      await screen.findByRole("menuitem", { name: /Create task from message/ }),
    );
    expect(await screen.findByDisplayValue("Order more agar by Friday")).toBeInTheDocument();
  });

  it("makes plain task text from a message", () => {
    expect(taskText("Ask @[Ada](user:00000000-0000-0000-0000-000000000000) about `x`")).toBe(
      "Ask Ada about x",
    );
  });
});

describe("link cards", () => {
  it("finds https links once, without code or sentence punctuation", () => {
    expect(
      messageLinks(
        "See https://github.com/lab/repo. and [notes](https://example.test/a) " +
          "`https://in.code/x` http://plain.test https://github.com/lab/repo",
      ),
    ).toEqual(["https://example.test/a", "https://github.com/lab/repo"]);
  });

  it("shows a known service and a previewed page under the message", async () => {
    mockFetch({
      ...world([
        msg({
          body: "Join https://meet.google.com/abc-defg-hij then read https://atlas.example.test/p",
        }),
      ]),
      [`GET ${L}/link-preview/?url=${encodeURIComponent("https://atlas.example.test/p")}`]: {
        body: {
          url: "https://atlas.example.test/p",
          host: "atlas.example.test",
          title: "Cell atlas",
          description: "A reference atlas",
          site_name: "",
        },
      },
    });
    renderRoute("/labs/lab1/chat");
    expect(await screen.findByRole("link", { name: "Google Meet" })).toHaveAttribute(
      "href",
      "https://meet.google.com/abc-defg-hij",
    );
    expect(await screen.findByRole("link", { name: "Cell atlas" })).toBeInTheDocument();
    expect(screen.getByText("A reference atlas")).toBeInTheDocument();
  });
});

describe("project chat and Google Chat", () => {
  const P = `${L}/projects/p1`;
  const project = {
    id: "p1",
    name: "Sleep",
    status: "active",
    description: "",
    my_permissions: ["view_project", "edit_project", "edit_content"],
  };
  const projectWorld = (google = status()) => ({
    ...world([]),
    [`GET ${L}/projects/`]: { body: [project] },
    [`GET ${P}/`]: { body: project },
    [`GET ${P}/messages/`]: { body: [] },
    [`POST ${P}/messages/read/`]: { status: 204 },
    [`GET ${P}/chat/google/`]: { body: google },
    [`GET ${P}/documents/`]: { body: [] },
    [`GET ${P}/datasets/`]: { body: [] },
    [`GET ${P}/analyses/`]: { body: [] },
    [`GET ${P}/results/`]: { body: [] },
    [`GET ${P}/decisions/`]: { body: [] },
    [`GET ${P}/manuscripts/`]: { body: [] },
  });

  it("links a project chat to a group chat", async () => {
    const calls = mockFetch({
      ...projectWorld(status({ connected: true, can_manage: true })),
      [`GET ${P}/chat/google/spaces/`]: {
        body: [{ name: "spaces/GRP1", display_name: "Dana, Eli", kind: "group_chat" }],
      },
      [`PUT ${P}/chat/google/`]: {
        body: status({
          bridge: { ...bridge, space: "spaces/GRP1", space_name: "Dana, Eli" },
          connected: true,
          can_manage: true,
        }),
      },
    });
    renderRoute("/labs/lab1/projects/p1/chat");
    await userEvent.click(await screen.findByRole("button", { name: "Google Chat options" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Sync with Google Chat" }));
    const dialog = await screen.findByRole("dialog", { name: "Sync with Google Chat" });
    await userEvent.click(within(dialog).getByRole("combobox"));
    const option = await screen.findByRole("option", { name: /Dana, Eli/ });
    expect(option).toHaveTextContent("Group chat");
    await userEvent.click(option);
    await userEvent.click(within(dialog).getByRole("button", { name: "Start syncing" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ space: "spaces/GRP1" }),
    );
  });

  it("says where a linked project chat's messages also go", async () => {
    mockFetch(projectWorld(status({ bridge: { ...bridge, space_name: "Dana, Eli" } })));
    renderRoute("/labs/lab1/projects/p1/chat");
    expect(
      await screen.findByText(/Messages are also sent to the Google Chat Dana, Eli/),
    ).toBeInTheDocument();
  });
});

describe("importing from Google Chat into a chat (D327)", () => {
  it("imports a group chat's latest messages into the lab chat", async () => {
    const calls = mockFetch({
      ...world([], status({ connected: true, can_manage: true }), [
        "view_lab",
        "manage_lab_integrations",
      ]),
      [`GET ${L}/chat/google/spaces/`]: {
        body: [{ name: "spaces/GRP1", display_name: "Dana, Eli", kind: "group_chat" }],
      },
      [`POST ${L}/chat/google/import/`]: { body: { imported: 2, skipped: 1 } },
    });
    renderRoute("/labs/lab1/chat");
    await userEvent.click(await screen.findByRole("button", { name: "Google Chat options" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Import messages" }));
    const dialog = await screen.findByRole("dialog", { name: "Import from Google Chat" });
    expect(within(dialog).getByText(/added to this chat as messages/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("combobox"));
    await userEvent.click(await screen.findByRole("option", { name: /Dana, Eli/ }));
    expect(within(dialog).getByText(/latest messages of this group chat/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Import" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith("/import/"))?.body).toEqual({
        space: "spaces/GRP1",
        thread: "",
      }),
    );
    expect(
      await screen.findByText("Imported 2 messages; 1 message were already here"),
    ).toBeInTheDocument();
  });

  it("is not offered to members who cannot link the chat", async () => {
    mockFetch(world([], status({ bridge, connected: true, can_manage: false })));
    renderRoute("/labs/lab1/chat");
    expect(await screen.findByText("Sleep lab")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Google Chat options" })).toBeNull();
  });
});
