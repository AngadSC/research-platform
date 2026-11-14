import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const at = "2026-01-01T00:00:00Z";
const recents = Array.from({ length: 9 }, (_, i) => ({
  url: `/labs/lab1/projects/p1/documents/d${i}`,
  label: `Doc number ${i}`,
  kind: "document",
  at,
}));

describe("Recent", () => {
  it("shows six, with the project's name under each title", async () => {
    mockFetch({
      [SESSION]: signedIn,
      "GET /api/me/": {
        body: { id: "u1", email: "ada@uni.edu", display_name: "Ada", preferences: { recents } },
      },
      "GET /api/labs/": { body: [makeLab(["view_lab"])] },
      "GET /api/labs/lab1/": { body: makeLab(["view_lab"]) },
      "GET /api/labs/lab1/projects/": {
        body: [{ id: "p1", name: "Gut study", color: "teal", status: "active" }],
      },
    });
    renderRoute("/labs/lab1/dashboard");
    expect(await screen.findByRole("link", { name: /Doc number 0/ })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Doc number/ })).toHaveLength(6);
    expect(screen.getAllByText(/Gut study/).length).toBeGreaterThanOrEqual(6);
  });
});
