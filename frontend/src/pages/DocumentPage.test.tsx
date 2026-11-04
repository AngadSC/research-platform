import { screen, waitFor } from "@testing-library/react";
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
  title,
  version,
  content: [],
  created_by: user,
  updated_by: user,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
});
const handlers = (perms: string[], extra: Record<string, unknown> = {}) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(["view_lab"])] },
  "GET /api/labs/lab1/projects/p1/": { body: project(perms) },
  "GET /api/labs/lab1/documents/d1/": { body: doc(3) },
  ...extra,
});
const EDIT = ["view_project", "edit_content"];
const DOC = "/labs/lab1/projects/p1/documents/d1";

describe("documents tab", () => {
  it("shows the empty state with a New document button", async () => {
    mockFetch({ ...handlers(EDIT), "GET /api/labs/lab1/projects/p1/documents/": { body: [] } });
    renderRoute("/labs/lab1/projects/p1/documents");
    expect(await screen.findByText("No documents yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New document" })).toBeInTheDocument();
  });
});

describe("document page", () => {
  it("saves with base_version", async () => {
    const calls = mockFetch(
      handlers(EDIT, { "PUT /api/labs/lab1/documents/d1/": { body: doc(4, "Renamed") } }),
    );
    renderRoute(DOC);
    const title = await screen.findByLabelText("Title");
    await userEvent.type(title, "!");
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument());
    const put = calls.find((c) => c.method === "PUT");
    expect(put?.body).toMatchObject({ title: "Protocol!", base_version: 3 });
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
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(
      await screen.findByText("This document changed since you opened it"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Bo saved version 7 on/)).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "PUT")).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: /Save anyway/ }));
    await waitFor(() => expect(calls.filter((c) => c.method === "PUT")).toHaveLength(2));
    expect(calls.filter((c) => c.method === "PUT")[1]?.body).toMatchObject({ base_version: 7 });
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
    await userEvent.click(await screen.findByRole("button", { name: "History" }));
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
  });
});
