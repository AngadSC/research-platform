import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const ev = (i: number) => ({
  id: `e${i}`,
  actor: { id: "u1", email: "ada@uni.edu", display_name: "Ada" },
  action: "membership.invited",
  target_type: "invite",
  target_id: null,
  target_label: `bob${i}@uni.edu`,
  ip: "10.0.0.1",
  created_at: new Date(Date.now() - 3600_000).toISOString(),
  metadata: { role: "member" },
});
const base = (perms: string[]) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(perms)] },
  "GET /api/labs/lab1/": { body: makeLab(perms) },
  "GET /api/labs/lab1/members/": { body: [] },
});
const EVENTS = "GET /api/labs/lab1/audit-events/?";

describe("audit log", () => {
  it("renders rows, loads more, opens details", async () => {
    const calls = mockFetch({
      ...base(["view_lab", "view_audit_log"]),
      [EVENTS]: {
        body: { next: "http://x/api/labs/lab1/audit-events/?cursor=abc", results: [ev(1)] },
      },
      [`${EVENTS}cursor=abc`]: { body: { next: null, results: [ev(2)] } },
    });
    renderRoute("/labs/lab1/audit-log");
    expect(await screen.findByText("bob1@uni.edu")).toBeInTheDocument();
    expect(screen.getByText("Invited a member")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("bob2@uni.edu")).toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith("cursor=abc"))).toBe(true);
    await userEvent.click(screen.getByText("bob1@uni.edu"));
    expect(await screen.findByText("Details")).toBeInTheDocument();
  });

  it("filter changes update the URL and the query", async () => {
    const calls = mockFetch({
      ...base(["view_audit_log"]),
      [EVENTS]: { body: { next: null, results: [ev(1)] } },
      [`${EVENTS}date_from=2026-01-02`]: { body: { next: null, results: [] } },
    });
    const router = renderRoute("/labs/lab1/audit-log");
    await screen.findByText("bob1@uni.edu");
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-01-02" } });
    await waitFor(() => expect(router.state.location.search).toBe("?date_from=2026-01-02"));
    expect(await screen.findByText("No matching activity")).toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith("?date_from=2026-01-02"))).toBe(true);
  });

  it("hides the nav entry and explains without the permission", async () => {
    mockFetch(base(["view_lab"]));
    renderRoute("/labs/lab1/audit-log");
    expect(await screen.findByText("You don't have access to the audit log")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Audit log" })).not.toBeInTheDocument();
  });

  it("shows the nav entry with the permission", async () => {
    mockFetch({
      ...base(["view_audit_log"]),
      [EVENTS]: { body: { next: null, results: [] } },
    });
    renderRoute("/labs/lab1/audit-log");
    expect(await screen.findByRole("link", { name: "Audit log" })).toBeInTheDocument();
  });
});
