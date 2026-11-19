import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn, pickMenuItem } from "@/test/utils";

// BlockNote needs a real browser; test our logic around it with a plain textarea.
vi.mock("@/components/documents/RichEditor", () => ({
  default: ({
    editable,
    label,
    onChange,
  }: {
    editable: boolean;
    label: string;
    onChange?: (b: unknown[]) => void;
  }) => (
    <div>
      <p>Quotable sentence here.</p>
      <textarea
        aria-label={label}
        readOnly={!editable}
        onChange={(e) => onChange?.([{ type: "paragraph", content: e.target.value }])}
      />
    </div>
  ),
}));

const user = { id: "u1", email: "ada@uni.edu", display_name: "Ada" };
const other = { id: "u2", email: "bo@uni.edu", display_name: "Bo" };
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
  my_project_role: "lead",
  my_permissions: perms,
});
const doc = (version: number, title = "Protocol") => ({
  id: "d1",
  project: "p1",
  folder: null,
  title,
  embed_url: "",
  embed_open_url: "",
  version,
  content: [],
  created_by: user,
  updated_by: user,
  retain_until: null,
  retention_note: "",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
});
const handlers = (perms: string[], extra: Record<string, unknown> = {}) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(["view_lab"])] },
  "GET /api/labs/lab1/projects/p1/": { body: project(perms) },
  "GET /api/labs/lab1/projects/p1/folders/": { body: [] },
  "GET /api/labs/lab1/projects/p1/documents/": { body: [] },
  "GET /api/labs/lab1/documents/d1/": { body: doc(3) },
  "GET /api/labs/lab1/documents/d1/comments/": { body: [] },
  ...extra,
});
const EDIT = ["view_project", "edit_content"];
const DOC = "/labs/lab1/projects/p1/documents/d1";
const TAB = "/labs/lab1/projects/p1/documents";
const openMenu = async () =>
  userEvent.click(await screen.findByRole("button", { name: "Document options" }));

describe("documents tab", () => {
  it("shows the empty state with a New document button", async () => {
    mockFetch(handlers(EDIT));
    renderRoute(TAB);
    expect(await screen.findByText("No documents or files yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New document" })).toBeInTheDocument();
  });

  it("deletes a document only after the confirmation dialog", async () => {
    const calls = mockFetch(
      handlers(EDIT, {
        "GET /api/labs/lab1/projects/p1/documents/": { body: [doc(3)] },
        "DELETE /api/labs/lab1/documents/d1/": { body: {} },
      }),
    );
    renderRoute(TAB);
    await userEvent.click(await screen.findByRole("button", { name: "Actions for Protocol" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Delete" }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await userEvent.click(await screen.findByRole("button", { name: "Delete document" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("filters documents by the folder in the URL and moves one to a folder", async () => {
    const folders = [
      {
        id: "f1",
        project: "p1",
        parent: null,
        name: "Protocols",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ];
    const calls = mockFetch(
      handlers(EDIT, {
        "GET /api/labs/lab1/projects/p1/folders/": { body: folders },
        "GET /api/labs/lab1/projects/p1/documents/": {
          body: [doc(3, "Root doc"), { ...doc(2, "Inside"), id: "d2", folder: "f1" }],
        },
        "POST /api/labs/lab1/documents/d1/move/": { body: {} },
      }),
    );
    renderRoute(TAB);
    expect(await screen.findByText("Root doc")).toBeInTheDocument();
    expect(screen.queryByText("Inside")).not.toBeInTheDocument();

    await userEvent.click(await screen.findByRole("button", { name: "Actions for Root doc" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Move to folder" }));
    await userEvent.selectOptions(await screen.findByLabelText("Folder"), "Protocols");
    await userEvent.click(screen.getByRole("button", { name: "Move" }));
    await waitFor(() =>
      expect(calls.find((c) => c.path.endsWith("/move/"))?.body).toEqual({ folder: "f1" }),
    );

    await userEvent.click(await screen.findByRole("link", { name: "Protocols" }));
    expect(await screen.findByText("Inside")).toBeInTheDocument();
    expect(screen.queryByText("Root doc")).not.toBeInTheDocument();
    expect(
      within(screen.getByRole("navigation", { name: "Folders" })).getByText("All"),
    ).toBeTruthy();
  });

  it("embeds a pasted link and shows a server rejection on the field", async () => {
    let n = 0;
    const calls = mockFetch(
      handlers(EDIT, {
        "POST /api/labs/lab1/projects/p1/documents/": () =>
          n++ === 0
            ? {
                status: 400,
                body: {
                  embed_url: ["Only Google Docs and Microsoft Office links can be embedded."],
                },
              }
            : {
                status: 201,
                body: { ...doc(1), embed_url: "https://docs.google.com/document/d/x/preview" },
              },
      }),
    );
    renderRoute(TAB);
    await pickMenuItem("More actions", "Embed a Google or Office doc");
    await userEvent.type(screen.getByLabelText("Title"), "Shared");
    await userEvent.type(screen.getByLabelText("Link"), "https://example.com/x");
    await userEvent.click(screen.getByRole("button", { name: "Embed" }));
    expect(await screen.findByText(/Only Google Docs/)).toBeInTheDocument();
    expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({
      title: "Shared",
      embed_url: "https://example.com/x",
    });
  });
});

describe("document page", () => {
  it("autosaves after a pause, with the autosave flag and base_version", async () => {
    const calls = mockFetch(
      handlers(EDIT, { "PUT /api/labs/lab1/documents/d1/": { body: doc(4, "Protocol!") } }),
    );
    renderRoute(DOC);
    const title = await screen.findByLabelText("Title");
    await userEvent.type(title, "!");
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true), {
      timeout: 6000,
    });
    const put = calls.find((c) => c.method === "PUT");
    expect(put?.body).toMatchObject({ title: "Protocol!", base_version: 3, autosave: true });
    expect(await screen.findByText("Saved")).toBeInTheDocument();
  });

  it("Ctrl+S saves now, without the autosave flag", async () => {
    const calls = mockFetch(
      handlers(EDIT, { "PUT /api/labs/lab1/documents/d1/": { body: doc(4, "Renamed") } }),
    );
    renderRoute(DOC);
    await userEvent.type(await screen.findByLabelText("Title"), "!");
    await userEvent.keyboard("{Control>}s{/Control}");
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({
      title: "Protocol!",
      base_version: 3,
      autosave: false,
    });
  });

  it("opens the conflict dialog on 409 and overwrites only when asked", async () => {
    let n = 0;
    const calls = mockFetch(
      handlers(EDIT, {
        "PUT /api/labs/lab1/documents/d1/": () =>
          n++ === 0
            ? {
                status: 409,
                body: {
                  detail: "changed",
                  code: "edit_conflict",
                  current_version: 7,
                  updated_by: other,
                  updated_at: "2026-02-01T10:00:00Z",
                },
              }
            : { body: doc(8) },
      }),
    );
    renderRoute(DOC);
    await userEvent.type(await screen.findByLabelText("Title"), "!");
    await userEvent.keyboard("{Control>}s{/Control}");
    expect(
      await screen.findByText("This document changed since you opened it"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Bo saved version 7 on/)).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "PUT")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: /Save anyway/ }));
    await waitFor(() => expect(calls.filter((c) => c.method === "PUT")).toHaveLength(2));
    expect(calls.filter((c) => c.method === "PUT")[1]?.body).toMatchObject({
      base_version: 7,
      autosave: false,
    });
  });

  it("saves on the way out and only warns when the save fails", async () => {
    let fail = false;
    const calls = mockFetch(
      handlers(EDIT, {
        "PUT /api/labs/lab1/documents/d1/": () =>
          fail ? { status: 500, body: { detail: "boom" } } : { body: doc(4) },
      }),
    );
    const router = renderRoute(DOC);
    await userEvent.type(await screen.findByLabelText("Title"), "!");
    void router.navigate(TAB);
    // Generous waits: under a full parallel run the save on the way out can take over a second.
    await waitFor(() => expect(router.state.location.pathname).toBe(TAB), { timeout: 5000 });
    expect(screen.queryByText("Leave without saving?")).not.toBeInTheDocument();
    await waitFor(() => expect(calls.filter((c) => c.method === "PUT")).toHaveLength(1));

    fail = true;
    void router.navigate(DOC);
    await userEvent.type(await screen.findByLabelText("Title"), "?");
    void router.navigate(TAB);
    expect(
      await screen.findByText("Leave without saving?", undefined, { timeout: 5000 }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Stay" }));
    expect(router.state.location.pathname).toBe(DOC);
  }, 20000);

  it("saves as soon as the title field is left", async () => {
    const calls = mockFetch(
      handlers(EDIT, { "PUT /api/labs/lab1/documents/d1/": () => ({ body: doc(4) }) }),
    );
    renderRoute(DOC);
    await userEvent.type(await screen.findByLabelText("Title"), "!");
    await userEvent.tab();
    await waitFor(() => expect(calls.filter((c) => c.method === "PUT")).toHaveLength(1), {
      timeout: 2000, // well under the 3 second autosave
    });
  });

  it("keeps History, Retention, Linked files and Delete behind one menu", async () => {
    const calls = mockFetch(
      handlers(EDIT, {
        "GET /api/labs/lab1/documents/d1/revisions/": { body: [] },
        "GET /api/labs/lab1/projects/p1/external-links/": { body: [] },
        "GET /api/labs/lab1/integrations/providers/": { body: [] },
        "DELETE /api/labs/lab1/documents/d1/": { body: {} },
      }),
    );
    const router = renderRoute(DOC);
    await openMenu();
    for (const name of ["History", "Retention", "Linked files", "Delete"]) {
      expect(await screen.findByRole("menuitem", { name })).toBeInTheDocument();
    }
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("menuitem", { name: "Delete" }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await userEvent.click(await screen.findByRole("button", { name: "Delete document" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    await waitFor(() => expect(router.state.location.pathname).toBe(TAB));
  });

  it("restores a revision after confirmation", async () => {
    const calls = mockFetch(
      handlers(EDIT, {
        "GET /api/labs/lab1/documents/d1/revisions/": {
          body: [
            {
              id: "r1",
              version: 2,
              title: "Protocol",
              created_by: other,
              created_at: "2026-02-01T10:00:00Z",
              restored_from_version: null,
            },
          ],
        },
        "GET /api/labs/lab1/documents/d1/revisions/2/": {
          body: {
            id: "r1",
            version: 2,
            title: "Protocol",
            created_by: other,
            created_at: "2026-02-01T10:00:00Z",
            restored_from_version: null,
            content: [],
          },
        },
        "POST /api/labs/lab1/documents/d1/revisions/2/restore/": { body: doc(4) },
      }),
    );
    renderRoute(DOC);
    await openMenu();
    await userEvent.click(await screen.findByRole("menuitem", { name: "History" }));
    await userEvent.click(await screen.findByRole("button", { name: /Version 2/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Restore this version" }));
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await userEvent.click(await screen.findByRole("button", { name: "Restore" }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.path.endsWith("/2/restore/"))).toBe(true),
    );
  });

  it("is read-only without edit_content", async () => {
    mockFetch(handlers(["view_project"]));
    renderRoute(DOC);
    expect(await screen.findByLabelText("Document content")).toHaveAttribute("readonly");
    expect(screen.getByLabelText("Title")).toHaveAttribute("readonly");
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    await openMenu();
    expect(await screen.findByText("You have read-only access.")).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Delete" })).not.toBeInTheDocument();
  });

  it("frames an embedded document, with a link that always opens it", async () => {
    mockFetch(
      handlers(EDIT, {
        "GET /api/labs/lab1/documents/d1/": {
          body: {
            ...doc(3),
            embed_url: "https://docs.google.com/document/d/x/preview",
            embed_open_url: "https://docs.google.com/document/d/x/edit",
          },
        },
      }),
    );
    renderRoute(DOC);
    const frame = await screen.findByTitle("Protocol");
    expect(frame).toHaveAttribute("src", "https://docs.google.com/document/d/x/preview");
    expect(frame.getAttribute("sandbox")).toContain("allow-scripts");
    expect(frame).toHaveAttribute("referrerpolicy", "no-referrer");
    expect(screen.getByRole("link", { name: "Open in Google Docs" })).toHaveAttribute(
      "href",
      "https://docs.google.com/document/d/x/edit",
    );
    expect(screen.queryByLabelText("Document content")).not.toBeInTheDocument();
  });
});

describe("leaving a blank new document", () => {
  const blank = { ...doc(1, "Untitled document"), content: [] };
  const run = async (d: unknown) => {
    const calls = mockFetch(
      handlers(EDIT, {
        "GET /api/labs/lab1/documents/d1/": { body: d },
        "DELETE /api/labs/lab1/documents/d1/": { body: {} },
      }),
    );
    const router = renderRoute(DOC);
    await screen.findByLabelText("Title");
    await router.navigate(TAB);
    await screen.findByText("No documents or files yet");
    await new Promise((r) => setTimeout(r, 20));
    return calls;
  };

  it("deletes it", async () => {
    expect((await run(blank)).some((c) => c.method === "DELETE")).toBe(true);
  });

  it("keeps a blank document made by someone else", async () => {
    expect((await run({ ...blank, created_by: other })).some((c) => c.method === "DELETE")).toBe(
      false,
    );
  });

  it("keeps a document that was ever saved", async () => {
    expect((await run({ ...blank, version: 2 })).some((c) => c.method === "DELETE")).toBe(false);
  });
});

describe("renaming a document", () => {
  it("updates the breadcrumb once the rename is saved", async () => {
    mockFetch(
      handlers(EDIT, {
        "GET /api/labs/lab1/documents/d1/": { body: doc(1, "Untitled document") },
        "PUT /api/labs/lab1/documents/d1/": (req: { body: unknown }) => ({
          body: doc(2, (req.body as { title: string }).title),
        }),
      }),
    );
    renderRoute(DOC);
    const title = await screen.findByLabelText("Title");
    const crumbs = screen.getByRole("navigation", { name: /breadcrumb/i });
    expect(within(crumbs).getByText("Untitled document")).toBeInTheDocument();
    await userEvent.clear(title);
    await userEvent.type(title, "Methods");
    expect(await within(crumbs).findByText("Methods", {}, { timeout: 6000 })).toBeInTheDocument();
  });
});

describe("document tasks and focus", () => {
  it("lists the tasks linked to the document and offers a task from it", async () => {
    mockFetch(
      handlers(EDIT, {
        "GET /api/labs/lab1/projects/p1/tasks/": {
          body: [
            {
              id: "t1",
              title: "Write-up 3 things",
              status: "todo",
              due_date: "2026-12-01",
              documents: [{ id: "d1", title: "Protocol" }],
              attachments: [],
            },
            { id: "t2", title: "Other", status: "todo", due_date: null, documents: [] },
          ],
        },
      }),
    );
    renderRoute(DOC);
    expect(await screen.findByRole("link", { name: /Write-up 3 things/ })).toHaveAttribute(
      "href",
      "/labs/lab1/projects/p1/tasks?task=t1",
    );
    expect(screen.queryByRole("link", { name: /Other/ })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Add a task from this document" }));
    expect(await screen.findByRole("heading", { name: "New task" })).toBeInTheDocument();
  });

  it("focus mode fills the window and exits again", async () => {
    mockFetch(handlers(EDIT));
    renderRoute(DOC);
    const focus = await screen.findByRole("button", { name: "Focus" });
    await userEvent.click(focus);
    expect(await screen.findByRole("button", { name: "Exit focus" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await userEvent.keyboard("{Escape}");
    expect(await screen.findByRole("button", { name: "Focus" })).toBeInTheDocument();
  });
});

describe("document comments", () => {
  const C = "/api/labs/lab1/documents/d1/comments/";
  const comment = (id: string, author: typeof user, extra: Record<string, unknown> = {}) => ({
    id,
    parent: null,
    author,
    body: `Note ${id}`,
    quote: "",
    resolved_at: null,
    resolved_by: null,
    created_at: "2026-01-02T00:00:00Z",
    ...extra,
  });
  const people = {
    "GET /api/me/": { body: user },
    "GET /api/labs/lab1/documents/d1/comment-people/": { body: [other] },
  };

  it("opens from the button and posts a comment with a mention", async () => {
    const calls = mockFetch(
      handlers(EDIT, { ...people, [`POST ${C}`]: { body: comment("c1", user) } }),
    );
    renderRoute(DOC);
    await userEvent.click(await screen.findByRole("button", { name: "Comments, 0 open" }));
    const panel = await screen.findByRole("complementary", { name: "Comments" });
    expect(within(panel).getByText(/No open comments/)).toBeInTheDocument();
    const box = within(panel).getByRole("textbox", { name: "Add a comment" });
    await userEvent.type(box, "Please check @b");
    await userEvent.keyboard("{Enter}");
    await userEvent.type(box, "the methods");
    await userEvent.click(within(panel).getByRole("button", { name: "Comment" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST" && c.path === C)?.body).toEqual({
        body: "Please check @[Bo](user:u2) the methods",
        quote: "",
      }),
    );
  });

  it("replies, resolves and deletes, and keeps resolved threads folded", async () => {
    const rows = [
      comment("c1", other, { quote: "the intro" }),
      comment("c2", user, { parent: "c1" }),
      comment("c3", other, { resolved_at: "2026-01-03T00:00:00Z", resolved_by: user }),
    ];
    const calls = mockFetch(
      handlers(EDIT, {
        ...people,
        [`GET ${C}`]: { body: rows },
        [`POST ${C}`]: { body: comment("c4", user, { parent: "c1" }) },
        [`PATCH ${C}c1/`]: { body: rows[0] },
        [`DELETE ${C}c2/`]: { status: 204 },
      }),
    );
    renderRoute(`${DOC}?comments=1`);
    const panel = await screen.findByRole("complementary", { name: "Comments" });
    expect(await within(panel).findByText("Note c1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Comments, 1 open" })).toBeInTheDocument();
    expect(within(panel).getByText("the intro")).toBeInTheDocument();
    expect(within(panel).queryByText("Note c3")).toBeNull();
    await userEvent.click(within(panel).getByRole("button", { name: "Show resolved (1)" }));
    expect(within(panel).getByText("Note c3")).toBeInTheDocument();

    await userEvent.click(within(panel).getByRole("button", { name: "Reply" }));
    await userEvent.type(within(panel).getByRole("textbox", { name: "Reply" }), "Fixed");
    await userEvent.click(within(panel).getByRole("button", { name: "Reply" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST" && c.path === C)?.body).toEqual({
        body: "Fixed",
        parent: "c1",
      }),
    );

    await userEvent.click(within(panel).getByRole("button", { name: "Resolve comment by Bo" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH" && c.path === `${C}c1/`)?.body).toEqual({
        resolved: true,
      }),
    );

    // Ada (an editor, not a lead) deletes her own reply but not Bo's comment
    expect(within(panel).queryByRole("button", { name: "Delete comment by Bo" })).toBeNull();
    await userEvent.click(within(panel).getByRole("button", { name: "Delete comment by Ada" }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await userEvent.click(within(panel).getByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "DELETE" && c.path === `${C}c2/`)).toBe(true),
    );
  });

  it("lets a viewer comment and resolve only their own", async () => {
    mockFetch(
      handlers(["view_project"], {
        ...people,
        [`GET ${C}`]: { body: [comment("c1", other), comment("c2", user)] },
      }),
    );
    renderRoute(`${DOC}?comments=1`);
    const panel = await screen.findByRole("complementary", { name: "Comments" });
    await within(panel).findByText("Note c1");
    expect(within(panel).getByRole("textbox", { name: "Add a comment" })).toBeInTheDocument();
    expect(within(panel).getAllByRole("button", { name: /^Resolve/ })).toHaveLength(1);
    expect(
      within(panel).getByRole("button", { name: "Resolve comment by Ada" }),
    ).toBeInTheDocument();
    expect(within(panel).getAllByRole("button", { name: /^Delete/ })).toHaveLength(1);
  });

  it("quotes the text selected before the comment box was clicked, and the quote can be cleared", async () => {
    const calls = mockFetch(
      handlers(EDIT, { ...people, [`POST ${C}`]: { body: comment("c1", user) } }),
    );
    renderRoute(`${DOC}?comments=1`);
    const panel = await screen.findByRole("complementary", { name: "Comments" });
    const sentence = await screen.findByText("Quotable sentence here.");
    document.getSelection()!.selectAllChildren(sentence);
    act(() => document.dispatchEvent(new Event("selectionchange")));
    const box = within(panel).getByRole("textbox", { name: "Add a comment" });
    await userEvent.click(box); // the selection is lost here
    expect(within(panel).getByText("Quotable sentence here.")).toBeInTheDocument();
    await userEvent.type(box, "Why?");
    await userEvent.click(within(panel).getByRole("button", { name: "Comment" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST" && c.path === C)?.body).toEqual({
        body: "Why?",
        quote: "Quotable sentence here.",
      }),
    );
    expect(within(panel).queryByRole("button", { name: "Remove quote" })).toBeNull();
  });

  it("offers the people who can read the document, picks one by click, focuses a reply", async () => {
    const calls = mockFetch(
      handlers(EDIT, {
        ...people,
        [`GET ${C}`]: { body: [comment("c1", other)] },
        [`POST ${C}`]: { body: comment("c2", user) },
      }),
    );
    renderRoute(`${DOC}?comments=1`);
    const panel = await screen.findByRole("complementary", { name: "Comments" });
    await userEvent.click(await within(panel).findByRole("button", { name: "Reply" }));
    const reply = within(panel).getByRole("textbox", { name: "Reply" });
    expect(reply).toHaveFocus();
    const box = within(panel).getByRole("textbox", { name: "Add a comment" });
    await userEvent.type(box, "Hi @b");
    await userEvent.click(await screen.findByRole("option", { name: "Bo" }));
    await userEvent.type(box, "ok");
    await userEvent.click(within(panel).getByRole("button", { name: "Comment" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST" && c.path === C)?.body).toEqual({
        body: "Hi @[Bo](user:u2) ok",
        quote: "",
      }),
    );
  });
});
