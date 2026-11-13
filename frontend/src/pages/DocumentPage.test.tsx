import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

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
    <textarea
      aria-label={label}
      readOnly={!editable}
      onChange={(e) => onChange?.([{ type: "paragraph", content: e.target.value }])}
    />
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
    await userEvent.click(
      await screen.findByRole("button", { name: "Embed a Google or Office doc" }),
    );
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
    await waitFor(() => expect(router.state.location.pathname).toBe(TAB));
    expect(screen.queryByText("Leave without saving?")).not.toBeInTheDocument();
    expect(calls.filter((c) => c.method === "PUT")).toHaveLength(1);

    fail = true;
    void router.navigate(DOC);
    await userEvent.type(await screen.findByLabelText("Title"), "?");
    void router.navigate(TAB);
    expect(await screen.findByText("Leave without saving?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Stay" }));
    expect(router.state.location.pathname).toBe(DOC);
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

  it("keeps a document that was ever saved", async () => {
    expect((await run({ ...blank, version: 2 })).some((c) => c.method === "DELETE")).toBe(false);
  });
});
