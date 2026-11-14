import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const user = { id: "u1", email: "ada@uni.edu", display_name: "Ada Lee" };
const proj = (id: string, name: string) => ({
  id,
  name,
  description: "",
  status: "active",
  color: "blue",
  my_permissions: ["view_project", "edit_content"],
});
function setup(extra: Record<string, unknown> = {}) {
  return mockFetch({
    [SESSION]: signedIn,
    "GET /api/me/": { body: user },
    "GET /api/labs/": { body: [makeLab(["view_lab"])] },
    "GET /api/labs/lab1/": { body: makeLab(["view_lab"]) },
    "GET /api/labs/lab1/projects/": { body: [proj("p1", "Paper 2"), proj("p2", "Thesis")] },
    "GET /api/labs/lab1/my-tasks/": { body: [] },
    "GET /api/labs/lab1/getting-started/": { status: 404, body: {} },
    "POST /api/labs/lab1/projects/p1/tasks/": { status: 201, body: { id: "t1" } },
    ...extra,
  });
}

describe("quick capture", () => {
  it("opens with the keyboard and makes a task from one line", async () => {
    const calls = setup();
    renderRoute("/labs/lab1/dashboard");
    await screen.findByRole("button", { name: "Add a task" });
    await userEvent.keyboard("{Control>}g{/Control}");
    const box = await screen.findByLabelText("Task");
    await userEvent.type(box, "email Dr. Bhalloo 2030-05-17 #paper2");
    expect(
      await within(await screen.findByRole("dialog")).findByText("Paper 2"),
    ).toBeInTheDocument();
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.method === "POST")!.body).toMatchObject({
      title: "email Dr. Bhalloo",
      due_date: "2030-05-17",
      assignee: "u1",
    });
  });

  it("says when a tag matches no project, and will not add an empty task", async () => {
    const calls = setup();
    renderRoute("/labs/lab1/dashboard");
    await userEvent.click(await screen.findByRole("button", { name: "Add a task" }));
    const box = await screen.findByLabelText("Task");
    await userEvent.type(box, "read #nothing");
    expect(await screen.findByText(/No project matches/)).toBeInTheDocument();
    await userEvent.clear(box);
    expect(screen.getByRole("button", { name: "Add task" })).toBeDisabled();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });
});
