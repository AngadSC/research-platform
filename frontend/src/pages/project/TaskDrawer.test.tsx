import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

// Radix Select and Dropdown want these in jsdom.
beforeAll(() => {
  Element.prototype.hasPointerCapture ||= () => false;
  Element.prototype.setPointerCapture ||= () => {};
  Element.prototype.releasePointerCapture ||= () => {};
});

const ada = { id: "u1", email: "ada@uni.edu", display_name: "Ada" };
const grace = { id: "u2", email: "grace@uni.edu", display_name: "Grace" };
const project = (perms: string[]) => ({
  id: "p1",
  name: "Gut study",
  description: "",
  status: "active",
  start_date: null,
  retain_until: null,
  retention_note: "",
  created_by: ada,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  my_project_role: "lead",
  my_permissions: perms,
});
const task = (extra: Record<string, unknown> = {}) => ({
  id: "t1",
  project: "p1",
  title: "Run assay",
  description: "Plate 3",
  assignee: ada,
  due_date: "2026-02-01",
  status: "todo",
  position: 0,
  created_by: ada,
  documents: [{ id: "d1", title: "Protocol", version: 1 }],
  attachments: [
    { id: "a1", original_filename: "raw.csv", content_type: "text/csv", size_bytes: 9 },
  ],
  post_count: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  ...extra,
});
const post = (id: string, author: typeof ada, body: string) => ({
  id,
  task: "t1",
  author,
  body,
  edited_at: null,
  created_at: "2026-01-02T10:00:00Z",
});
const member = (user: typeof ada, role: string) => ({
  id: `m-${user.id}`,
  project: "p1",
  user,
  role,
  created_at: "2026-01-01T00:00:00Z",
});
const LAB = "/api/labs/lab1";
const P = `${LAB}/projects/p1`;

function base(perms: string[], posts: unknown[] = [], prefs?: unknown) {
  return {
    [SESSION]: signedIn,
    "GET /api/me/": { body: { ...ada, preferences: prefs } },
    "GET /api/labs/": { body: [makeLab(["view_lab"])] },
    [`GET ${LAB}/`]: { body: makeLab(["view_lab"]) },
    [`GET ${LAB}/projects/`]: { body: [project(perms)] },
    [`GET ${P}/`]: { body: project(perms) },
    [`GET ${P}/tasks/`]: { body: [task()] },
    [`GET ${P}/members/`]: {
      body: [
        member(ada, "lead"),
        member(grace, "contributor"),
        member({ ...grace, id: "u3", email: "v@u.edu", display_name: "Vera" }, "viewer"),
      ],
    },
    [`GET ${P}/deadlines/`]: { body: [] },
    [`GET ${P}/documents/`]: {
      body: [
        { id: "d1", title: "Protocol", version: 1, updated_by: ada },
        { id: "d2", title: "Budget", version: 1, updated_by: ada },
      ],
    },
    [`GET ${P}/attachments/`]: { body: [] },
    [`GET ${LAB}/tasks/t1/posts/`]: { body: posts },
  };
}
const TASKS = "/labs/lab1/projects/p1/tasks?view=list&task=t1";

describe("task drawer", () => {
  it("opens from a task and shows details, files and the thread", async () => {
    mockFetch(base(["view_project", "edit_content"], [post("x1", grace, "Plates arrived")]));
    renderRoute("/labs/lab1/projects/p1/tasks?view=list");
    await userEvent.click(await screen.findByRole("cell", { name: "Run assay" }));
    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByLabelText("Title")).toHaveValue("Run assay");
    expect(within(drawer).getByLabelText("Description")).toHaveValue("Plate 3");
    expect(within(drawer).getByLabelText("Due date")).toHaveValue("2026-02-01");
    expect(within(drawer).getByRole("link", { name: /Protocol/ })).toHaveAttribute(
      "href",
      "/labs/lab1/projects/p1/documents/d1",
    );
    expect(within(drawer).getByRole("link", { name: /raw\.csv/ })).toBeInTheDocument();
    expect(await within(drawer).findByText("Plates arrived")).toBeInTheDocument();
  });

  it("stops the title at the server's 300-character limit", async () => {
    mockFetch(base(["view_project", "edit_content"]));
    renderRoute("/labs/lab1/projects/p1/tasks?view=list");
    await userEvent.click(await screen.findByRole("cell", { name: "Run assay" }));
    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByLabelText("Title")).toHaveAttribute("maxLength", "300");
  });

  it("changes the status and the assignee, offering only people who can edit", async () => {
    const calls = mockFetch({
      ...base(["view_project", "edit_content"]),
      [`PATCH ${LAB}/tasks/t1/`]: { body: task({ status: "done" }) },
    });
    const taskPatches = () =>
      calls.filter((c) => c.path === `${LAB}/tasks/t1/` && c.method === "PATCH");
    renderRoute(TASKS);
    const drawer = await screen.findByRole("dialog");
    await userEvent.click(within(drawer).getByRole("combobox", { name: "Assignee" }));
    const names = (await screen.findAllByRole("option")).map((o) => o.textContent);
    expect(names).toEqual(["Unassigned", "Ada", "Grace"]); // Vera is a viewer
    await userEvent.click(screen.getByRole("option", { name: "Grace" }));
    await waitFor(() => expect(taskPatches().at(0)?.body).toEqual({ assignee: "u2" }));
    await userEvent.click(within(drawer).getByRole("combobox", { name: "Status" }));
    await userEvent.click(await screen.findByRole("option", { name: "Done" }));
    await waitFor(() => expect(taskPatches().at(-1)?.body).toEqual({ status: "done" }));
  });

  it("saves the title, description and due date when you leave the field", async () => {
    const calls = mockFetch({
      ...base(["view_project", "edit_content"]),
      [`PATCH ${LAB}/tasks/t1/`]: { body: task({ title: "Run the assay" }) },
    });
    const patches = () =>
      calls.filter((c) => c.path === `${LAB}/tasks/t1/` && c.method === "PATCH");
    renderRoute(TASKS);
    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).queryByRole("button", { name: "Save details" })).toBeNull();
    const title = within(drawer).getByLabelText("Title");
    await userEvent.click(title);
    await userEvent.type(title, " now");
    expect(patches()).toHaveLength(0); // nothing until you leave the field
    await userEvent.tab();
    await waitFor(() => expect(patches().at(0)?.body).toEqual({ title: "Run assay now" }));
    await userEvent.clear(within(drawer).getByLabelText("Due date"));
    await userEvent.tab();
    await waitFor(() => expect(patches().at(-1)?.body).toEqual({ due_date: null }));
  });

  it("does not save an unchanged field or an empty title", async () => {
    const calls = mockFetch(base(["view_project", "edit_content"]));
    renderRoute(TASKS);
    const drawer = await screen.findByRole("dialog");
    const title = within(drawer).getByLabelText("Title");
    await userEvent.click(title);
    await userEvent.tab();
    await userEvent.clear(title);
    await userEvent.tab();
    expect(await within(drawer).findByText("Enter a title")).toBeInTheDocument();
    expect(calls.filter((c) => c.path === `${LAB}/tasks/t1/` && c.method === "PATCH")).toEqual([]);
  });

  it("opens with the cursor in the title, not the text selected", async () => {
    mockFetch(base(["view_project", "edit_content"]));
    renderRoute(TASKS);
    const title = (await screen.findByLabelText("Title")) as HTMLInputElement;
    await waitFor(() => expect(title).toHaveFocus());
    await waitFor(() => expect(title.selectionStart).toBe(title.selectionEnd));
  });

  it("deletes only after confirming", async () => {
    const calls = mockFetch({
      ...base(["view_project", "edit_content"]),
      [`DELETE ${LAB}/tasks/t1/`]: { status: 204 },
    });
    renderRoute(TASKS);
    const drawer = await screen.findByRole("dialog");
    await userEvent.click(within(drawer).getByRole("button", { name: "Delete task" }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await userEvent.click(within(drawer).getByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("is read-only for a viewer: no controls, no composer, thread still readable", async () => {
    mockFetch(base(["view_project"], [post("x1", grace, "FYI")]));
    renderRoute(TASKS);
    const drawer = await screen.findByRole("dialog");
    expect(await within(drawer).findByText("FYI")).toBeInTheDocument();
    expect(within(drawer).queryByLabelText("Write an update")).not.toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "Delete task" })).not.toBeInTheDocument();
    expect(
      within(drawer).queryByRole("button", { name: "Attach existing" }),
    ).not.toBeInTheDocument();
  });

  it("attaches an existing document and detaches a file", async () => {
    const calls = mockFetch({
      ...base(["view_project", "edit_content"]),
      [`POST ${LAB}/tasks/t1/documents/`]: { body: task() },
      [`DELETE ${LAB}/tasks/t1/attachments/a1/`]: { body: task({ attachments: [] }) },
    });
    renderRoute(TASKS);
    const drawer = await screen.findByRole("dialog");
    await userEvent.click(within(drawer).getByRole("button", { name: "Attach existing" }));
    expect(screen.queryByRole("menuitem", { name: "Protocol" })).not.toBeInTheDocument(); // linked
    await userEvent.click(await screen.findByRole("menuitem", { name: "Budget" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ id: "d2" }));
    await userEvent.click(within(drawer).getByRole("button", { name: "Detach raw.csv" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });
});

describe("task thread", () => {
  it("lists updates oldest first with author and time, rendering text safely", async () => {
    mockFetch(
      base(
        ["view_project", "edit_content"],
        [post("x1", grace, "**Done** with plate 1"), post("x2", ada, "<script>alert(1)</script>")],
      ),
    );
    renderRoute(TASKS);
    const thread = await screen.findByRole("region", { name: "Updates" });
    const items = await within(thread).findAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Grace");
    expect(items[0]!.querySelector("strong:not(:first-child), strong + *")).not.toBeNull();
    expect(items[1]).toHaveTextContent("<script>alert(1)</script>");
    expect(thread.querySelector("script")).toBeNull();
    expect(within(thread).getAllByRole("time").length).toBe(2);
  });

  it("posts an update from the composer", async () => {
    const calls = mockFetch({
      ...base(["view_project", "edit_content"]),
      [`POST ${LAB}/tasks/t1/posts/`]: { status: 201, body: post("x9", ada, "Started") },
    });
    renderRoute(TASKS);
    const thread = await screen.findByRole("region", { name: "Updates" });
    const send = within(thread).getByRole("button", { name: "Post update" });
    expect(send).toBeDisabled();
    await userEvent.type(within(thread).getByLabelText("Write an update"), "Started");
    await userEvent.click(send);
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({ body: "Started" }),
    );
    expect(await screen.findByText("Update posted")).toBeInTheDocument();
  });

  it("lets authors edit and delete their own posts, and leads delete any", async () => {
    mockFetch(
      base(
        ["view_project", "edit_content", "edit_project"],
        [post("x1", ada, "mine"), post("x2", grace, "theirs")],
      ),
    );
    renderRoute(TASKS);
    const thread = await screen.findByRole("region", { name: "Updates" });
    await within(thread).findByText("mine");
    expect(within(thread).getAllByRole("button", { name: /^Edit/ })).toHaveLength(1);
    expect(within(thread).getAllByRole("button", { name: /^Delete/ })).toHaveLength(2);
  });

  it("a non-lead sees delete only on their own posts", async () => {
    mockFetch(
      base(
        ["view_project", "edit_content"],
        [post("x1", ada, "mine"), post("x2", grace, "theirs")],
      ),
    );
    renderRoute(TASKS);
    const thread = await screen.findByRole("region", { name: "Updates" });
    await within(thread).findByText("mine");
    expect(within(thread).getAllByRole("button", { name: /^Delete/ })).toHaveLength(1);
  });
});

describe("default task view", () => {
  it("is the board without a saved preference", async () => {
    mockFetch(base(["view_project"], [], {}));
    renderRoute("/labs/lab1/projects/p1/tasks");
    expect(await screen.findByRole("region", { name: "To do" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("is the list when preferences.task_view is list", async () => {
    mockFetch(base(["view_project"], [], { task_view: "list" }));
    renderRoute("/labs/lab1/projects/p1/tasks");
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });

  it("colours board columns and cards by status", async () => {
    mockFetch(base(["view_project"], [], { task_view: "board" }));
    renderRoute("/labs/lab1/projects/p1/tasks");
    const col = await screen.findByRole("region", { name: "To do" });
    expect(col).toHaveAttribute("data-status", "todo");
    expect(col).toHaveStyle({ backgroundColor: "#fef08a" });
    expect(screen.getByRole("region", { name: "Done" })).toHaveStyle({
      backgroundColor: "#bbf7d0",
    });
    expect(col.querySelector("article")).toHaveAttribute("data-status", "todo");
  });
});
