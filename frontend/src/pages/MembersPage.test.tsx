import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const at = "2026-01-01T00:00:00Z";
const ada = { id: "u1", email: "ada@uni.edu", display_name: "Ada" };
const invite = {
  id: "i1",
  email: "new@example.test",
  role: "member",
  expires_at: "2030-01-01T00:00:00Z",
  created_at: at,
  invited_by: ada,
};

describe("pending invitations", () => {
  it("shows the role as a select and confirms before revoking", async () => {
    const calls = mockFetch({
      [SESSION]: signedIn,
      "GET /api/labs/": { body: [] },
      "GET /api/me/": { body: ada },
      "GET /api/labs/lab1/": { body: makeLab(["view_lab", "manage_members"]) },
      "GET /api/labs/lab1/members/": {
        body: [{ id: "m1", user: ada, role: "pi", created_at: at }],
      },
      "GET /api/labs/lab1/invites/": { body: [invite] },
      "DELETE /api/labs/lab1/invites/i1/": { status: 204 },
    });
    renderRoute("/labs/lab1/members");
    expect(
      await screen.findByRole("combobox", { name: "Role for the invitation to new@example.test" }),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Revoke invitation for new@example.test" }),
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Revoke the invitation to new@example.test?");
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await userEvent.click(within(dialog).getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });
});
