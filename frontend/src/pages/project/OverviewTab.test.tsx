import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const at = "2026-01-01T00:00:00Z";
const ada = { id: "u1", email: "ada@uni.edu", display_name: "Ada" };
const vic = { id: "u2", email: "vic@uni.edu", display_name: "Vic" };
const project = (perms: string[], status = "active") => ({
  id: "p1",
  name: "Gut study",
  description: "",
  status,
  start_date: null,
  retain_until: null,
  retention_note: "",
  created_by: ada,
  created_at: at,
  updated_at: at,
  my_project_role: "lead",
  my_permissions: perms,
});
const setup = (perms: string[], extra = {}) =>
  mockFetch({
    [SESSION]: signedIn,
    "GET /api/labs/": { body: [] },
    "GET /api/me/": { body: ada },
    "GET /api/labs/lab1/": { body: makeLab(["view_lab"]) },
    "GET /api/labs/lab1/members/": {
      body: [
        { id: "m1", user: ada, role: "member", created_at: at },
        { id: "m2", user: vic, role: "viewer", created_at: at },
      ],
    },
    "GET /api/labs/lab1/projects/": { body: [project(perms)] },
    "GET /api/labs/lab1/projects/p1/": { body: project(perms) },
    "GET /api/labs/lab1/projects/p1/deadlines/": {
      body: [
        {
          id: "d1",
          title: "Ethics renewal",
          due_date: "2030-01-01",
          priority: "high",
          done: false,
        },
      ],
    },
    "GET /api/labs/lab1/projects/p1/members/": {
      body: [{ id: "pm1", project: "p1", user: vic, role: "contributor", created_at: at }],
    },
    ...extra,
  });

describe("project overview", () => {
  it("says what a lab viewer can really do on the project", async () => {
    setup(["view_project", "manage_project_members"]);
    renderRoute("/labs/lab1/projects/p1/overview");
    expect(
      await screen.findByText("Vic is a lab Viewer, so they can only read here."),
    ).toBeInTheDocument();
  });

  it("names the deadline in every row action", async () => {
    setup(["view_project", "edit_project"]);
    renderRoute("/labs/lab1/projects/p1/overview");
    for (const name of ["Mark done", "Edit", "Remove"])
      expect(
        await screen.findByRole("button", { name: `${name} Ethics renewal` }),
      ).toBeInTheDocument();
  });

  it("shows funding to PIs only, and never asks for it otherwise", async () => {
    const calls = setup(["view_project", "edit_project", "delete_project"]);
    renderRoute("/labs/lab1/projects/p1/overview");
    await screen.findByRole("button", { name: "Mark done Ethics renewal" });
    expect(screen.queryByRole("heading", { name: "Funding" })).not.toBeInTheDocument();
    expect(calls.some((c) => c.path.includes("/funding/"))).toBe(false);
  });

  it("lists funding for a PI", async () => {
    setup(["view_project", "edit_project", "access_funding"], {
      "GET /api/labs/lab1/projects/p1/funding/": {
        body: [
          {
            id: "f1",
            funder: "Example Funder",
            program: "Pilot",
            status: "active",
            end_date: null,
          },
        ],
      },
    });
    renderRoute("/labs/lab1/projects/p1/overview");
    const section = (await screen.findByRole("heading", { name: "Funding" })).closest("section")!;
    expect(await within(section).findByText("Example Funder, Pilot")).toBeInTheDocument();
  });

  it("lets a lead archive, and says who can delete", async () => {
    const calls = setup(["view_project", "edit_project"], {
      "PATCH /api/labs/lab1/projects/p1/": { body: project(["view_project"], "archived") },
    });
    renderRoute("/labs/lab1/projects/p1/overview");
    await userEvent.click(await screen.findByRole("button", { name: "Archive project" }));
    expect(screen.getByText(/ask a PI or lab admin/)).toBeInTheDocument();
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Archive" }),
    );
    await waitFor(() =>
      expect(
        calls.find((c) => c.method === "PATCH" && c.path.endsWith("/projects/p1/"))?.body,
      ).toEqual({ status: "archived" }),
    );
  });

  it("offers no archive without edit_project", async () => {
    setup(["view_project"]);
    renderRoute("/labs/lab1/projects/p1/overview");
    await screen.findByText("Ethics renewal");
    expect(screen.queryByRole("button", { name: "Archive project" })).not.toBeInTheDocument();
  });
});
