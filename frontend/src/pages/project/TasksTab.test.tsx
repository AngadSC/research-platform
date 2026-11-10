import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const user = { id: "u1", email: "ada@uni.edu", display_name: "Ada" };
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
const task = (id: string, title: string, status = "todo", position = 0) => ({
  id,
  project: "p1",
  title,
  description: "",
  assignee: null,
  due_date: null,
  status,
  position,
  created_by: user,
  documents: [],
  attachments: [],
  post_count: 0,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});
const base = (perms: string[], tasks: unknown[] = []) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(["view_lab", "create_project"])] },
  "GET /api/labs/lab1/": { body: makeLab(["view_lab", "create_project"]) },
  "GET /api/labs/lab1/projects/": { body: [project(perms)] },
  "GET /api/labs/lab1/projects/p1/": { body: project(perms) },
  "GET /api/labs/lab1/projects/p1/tasks/": { body: tasks },
  "GET /api/labs/lab1/projects/p1/members/": {
    body: [{ id: "m1", project: "p1", user, role: "lead", created_at: "2026-01-01T00:00:00Z" }],
  },
  "GET /api/labs/lab1/projects/p1/deadlines/": { body: [] },
});
const TASKS = "/labs/lab1/projects/p1/tasks";

describe("projects", () => {
  it("lists projects and shows the empty state", async () => {
    mockFetch(base(["view_project"]));
    renderRoute("/labs/lab1/projects");
    expect(await screen.findByRole("cell", { name: "Gut study" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "New project" }).length).toBeGreaterThan(0);
  });

  it("shows the empty state with no projects", async () => {
    mockFetch({ ...base([]), "GET /api/labs/lab1/projects/": { body: [] } });
    renderRoute("/labs/lab1/projects");
    expect(await screen.findByText("No projects yet")).toBeInTheDocument();
  });

  it("hides edit and delete without permission, shows them with it", async () => {
    mockFetch(base(["view_project"]));
    renderRoute("/labs/lab1/projects/p1");
    expect(await screen.findByRole("heading", { name: "Gut study" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
  });

  it("shows edit and delete with permission", async () => {
    mockFetch(base(["view_project", "edit_project", "delete_project"]));
    renderRoute("/labs/lab1/projects/p1");
    expect(await screen.findByRole("button", { name: "Edit" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(await screen.findByText(/soft delete/)).toBeInTheDocument();
  });
});

describe("tasks", () => {
  it("validates the title inline", async () => {
    const calls = mockFetch(base(["edit_content"], [task("t1", "Seed")]));
    renderRoute(`${TASKS}?new=task`);
    await userEvent.click(await screen.findByRole("button", { name: "Save" }));
    expect(await screen.findByText("Enter a title")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("moves a task with the menu, and rolls back on error", async () => {
    let fail = false;
    let status = "todo"; // what the "server" holds
    const calls = mockFetch({
      ...base(["edit_content"]),
      "GET /api/labs/lab1/projects/p1/tasks/": () => ({ body: [task("t1", "Seed", status)] }),
      "PATCH /api/labs/lab1/tasks/t1/": () => {
        if (fail) return { status: 500, body: null };
        status = "in_progress";
        return { body: task("t1", "Seed", status) };
      },
    });
    renderRoute(`${TASKS}?view=board`);
    const open = async () => {
      await userEvent.click(await screen.findByRole("button", { name: "Move Seed" }));
      await userEvent.click(await screen.findByRole("menuitem", { name: "Move to In progress" }));
    };
    await open();
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
        status: "in_progress",
        position: 0,
      }),
    );
    // Rolls back: server refuses the second move.
    fail = true;
    const col = (n: string) => screen.getByRole("region", { name: n });
    await waitFor(() => expect(col("In progress")).toHaveTextContent("Seed"));
    await userEvent.click(await screen.findByRole("button", { name: "Move Seed" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Move to Done" }));
    await waitFor(() => expect(col("In progress")).toHaveTextContent("Seed"));
    expect(col("Done")).not.toHaveTextContent("Seed");
  });

  it("opens the board by default and toggles to the list, saving the choice", async () => {
    const calls = mockFetch({
      ...base(["edit_content"], [task("t1", "Seed")]),
      "PATCH /api/me/": { body: { ...user, preferences: { task_view: "list" } } },
    });
    const router = renderRoute(TASKS);
    expect(await screen.findByRole("region", { name: "To do" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "List" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH" && c.path === "/api/me/")?.body).toEqual({
        preferences: { task_view: "list" },
      }),
    );
    expect(router.state.location.search).toBe("");
  });

  it("shows an empty state", async () => {
    mockFetch(base(["edit_content"]));
    renderRoute(TASKS);
    expect(await screen.findByText("No tasks yet")).toBeInTheDocument();
  });
});

describe("task delete", () => {
  const open = async (perms: string[], extra = {}) => {
    mockFetch({ ...base(perms, [task("t1", "Write intro")]), ...extra });
    renderRoute(`${TASKS}?view=list`);
    const u = userEvent.setup();
    await u.click(await screen.findByRole("cell", { name: "Write intro" }));
    return u;
  };

  it("deletes optimistically after confirmation", async () => {
    let gone = false;
    const u = await open(["edit_content"], {
      "GET /api/labs/lab1/projects/p1/tasks/": () => ({
        body: gone ? [] : [task("t1", "Write intro")],
      }),
      "DELETE /api/labs/lab1/tasks/t1/": () => {
        gone = true;
        return { status: 204 };
      },
    });
    await u.click(await screen.findByRole("button", { name: "Delete task" }));
    await u.click(screen.getByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(screen.queryByRole("cell", { name: "Write intro" })).toBeNull());
  });

  it("rolls back when the server refuses", async () => {
    const u = await open(["edit_content"], {
      "DELETE /api/labs/lab1/tasks/t1/": { status: 403, body: {} },
    });
    await u.click(await screen.findByRole("button", { name: "Delete task" }));
    await u.click(screen.getByRole("button", { name: "Confirm delete" }));
    expect(await screen.findByRole("cell", { name: "Write intro" })).toBeInTheDocument();
  });
});
