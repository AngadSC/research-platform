import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { ProjectFormDialog } from "@/pages/project/ProjectFormDialog";
import { mockFetch } from "@/test/utils";

const user = (id: string, name: string) => ({
  id,
  email: `${id}@example.test`,
  display_name: name,
});
const at = "2026-01-01T00:00:00Z";
const members = [
  { id: "m1", user: user("me", "Ada"), role: "pi", created_at: at },
  { id: "m2", user: user("u2", "Ben"), role: "member", created_at: at },
  { id: "m3", user: user("u3", "Cleo"), role: "member", created_at: at },
  { id: "m4", user: user("u4", "Visitor"), role: "viewer", created_at: at },
];

function open(onSave = vi.fn().mockResolvedValue(undefined)) {
  mockFetch({
    "GET /api/me/": { body: user("me", "Ada") },
    "GET /api/labs/lab1/members/": { body: members },
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/labs/lab1/projects"]}>
        <Routes>
          <Route
            path="/labs/:labId/projects"
            element={
              <ProjectFormDialog
                open
                onOpenChange={() => {}}
                canRetention={false}
                onSave={onSave}
              />
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return onSave;
}

describe("New project dialog: team and template", () => {
  it("says how many tasks a template makes and that they start unassigned", async () => {
    open();
    expect(screen.queryByText(/tasks will be created/)).toBeNull();
    await userEvent.click(screen.getByRole("combobox", { name: "Start from" }));
    await userEvent.click(await screen.findByRole("option", { name: /Honours thesis/ }));
    expect(
      screen.getByText("9 tasks will be created; assign them on the Tasks tab."),
    ).toBeInTheDocument();
  });

  it("sends the chosen lead and members, never yourself or a viewer", async () => {
    const onSave = open();
    await userEvent.type(screen.getByLabelText("Name"), "Sleep study");
    expect(await screen.findByRole("checkbox", { name: "Ben" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Ada" })).toBeNull();
    expect(screen.queryByRole("checkbox", { name: "Visitor" })).toBeNull();
    await userEvent.click(screen.getByRole("checkbox", { name: "Ben" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Cleo" }));
    await userEvent.click(screen.getByRole("combobox", { name: "Lead" }));
    await userEvent.click(await screen.findByRole("option", { name: "Cleo" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    const sent = onSave.mock.calls[0]![0];
    expect(sent.lead).toBe("u3");
    expect(sent.members).toEqual(["u2"]); // Cleo is the lead, so not also a member
  });
});
