import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fullDate } from "@/lib/format";
import { makeLab, mockFetch, openSidebarGroup, renderRoute, SESSION, signedIn } from "@/test/utils";

const ev = (i: number) => ({
  id: `e${i}`,
  actor: { id: "u1", email: "ada@uni.edu", display_name: "Ada" },
  action: "membership.invited",
  target_type: "invite",
  target_id: null,
  target_label: `bob${i}@uni.edu`,
  created_at: new Date(Date.now() - 3600_000).toISOString(),
  metadata: { role: "member" },
});
const base = (perms: string[]) => ({
  [SESSION]: signedIn,
  "GET /api/labs/": { body: [makeLab(perms)] },
  "GET /api/labs/lab1/": { body: makeLab(perms) },
  "GET /api/labs/lab1/members/": { body: [] },
});
const EVENTS = "GET /api/labs/lab1/audit-events/?changes_only=true";
const ALL = "GET /api/labs/lab1/audit-events/?";

describe("audit log", () => {
  it("renders rows, loads more, opens details", async () => {
    const calls = mockFetch({
      ...base(["view_lab", "view_audit_log"]),
      [EVENTS]: {
        body: { next: "http://x/api/labs/lab1/audit-events/?cursor=abc", results: [ev(1)] },
      },
      [`${EVENTS}&cursor=abc`]: { body: { next: null, results: [ev(2)] } },
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

  it("shows a dash for an empty target and plain words for every action", async () => {
    mockFetch({
      ...base(["view_audit_log"]),
      [EVENTS]: {
        body: {
          next: null,
          results: [
            { ...ev(1), action: "institution_resource.created", target_label: "" },
            { ...ev(2), action: "not_in_the_list.changed" },
          ],
        },
      },
    });
    renderRoute("/labs/lab1/audit-log");
    expect(await screen.findByText("Added an institution resource")).toBeInTheDocument();
    expect(screen.getByText("Not in the list changed")).toBeInTheDocument();
    expect(screen.queryByText("\ufffd")).not.toBeInTheDocument();
    const row = screen.getByText("Added an institution resource").closest("tr")!;
    expect(row).toHaveTextContent("—");
    await userEvent.click(screen.getByText("Added an institution resource"));
    expect(await screen.findByText("Invite")).toBeInTheDocument(); // the target's kind
    expect(screen.queryByText(/institution_resource/)).not.toBeInTheDocument();
  });

  it("names the target's kind and shows amounts in words, without ids", async () => {
    mockFetch({
      ...base(["view_audit_log"]),
      [EVENTS]: {
        body: {
          next: null,
          results: [
            {
              ...ev(1),
              action: "inventory.used",
              target_type: "labs.InventoryItem",
              target_label: "Ethanol 70%",
              metadata: {
                amount: "8.000000",
                unit: "bottles",
                deducted: "8.000000",
                usage: "f7a0464b-0e94-4f8b-8b8f-0c40db095284",
                changed: ["quantity", "low_stock_at"],
              },
            },
          ],
        },
      },
    });
    renderRoute("/labs/lab1/audit-log");
    await userEvent.click(await screen.findByText("Took stock from an inventory item"));
    const panel = await screen.findByRole("dialog");
    expect(panel).toHaveTextContent("Inventory itemEthanol 70%");
    expect(panel).toHaveTextContent("Amount8 bottles");
    expect(panel).toHaveTextContent("Changedquantity, low stock at");
    expect(panel).not.toHaveTextContent("Labs.InventoryItem");
    expect(panel).not.toHaveTextContent("f7a0464b");
    expect(panel).not.toHaveTextContent("Deducted");
  });

  it("adds a short detail line to stock and order events", async () => {
    mockFetch({
      ...base(["view_audit_log"]),
      [EVENTS]: {
        body: {
          next: null,
          results: [
            { ...ev(1), action: "inventory.used", metadata: { amount: "60.000000", unit: "mL" } },
            {
              ...ev(2),
              action: "inventory_order.updated",
              metadata: { changed: ["status"], status_from: "ordered", status_to: "received" },
            },
            { ...ev(3), action: "inventory_item.updated", metadata: { changed: ["status"] } },
          ],
        },
      },
    });
    renderRoute("/labs/lab1/audit-log");
    expect(await screen.findByText("Took 60 mL")).toBeInTheDocument();
    expect(screen.getByText("Status: ordered → received")).toBeInTheDocument();
    expect(screen.getByText("Changed: status")).toBeInTheDocument();
  });

  it("names old membership targets by role instead of showing their id", async () => {
    mockFetch({
      ...base(["view_audit_log"]),
      [EVENTS]: {
        body: {
          next: null,
          results: [{ ...ev(1), target_label: "0d01f826-2e1a-469b-ac4c-1bafeb44b150 is viewer" }],
        },
      },
    });
    renderRoute("/labs/lab1/audit-log");
    expect(await screen.findByText("A lab member (Viewer)")).toBeInTheDocument();
  });

  it("filter changes update the URL and the query", async () => {
    const calls = mockFetch({
      ...base(["view_audit_log"]),
      [EVENTS]: { body: { next: null, results: [ev(1)] } },
      [`${ALL}date_from=2026-01-02&changes_only=true`]: { body: { next: null, results: [] } },
    });
    const router = renderRoute("/labs/lab1/audit-log");
    await screen.findByText("bob1@uni.edu");
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-01-02" } });
    await waitFor(() => expect(router.state.location.search).toBe("?date_from=2026-01-02"));
    expect(await screen.findByText("No matching activity")).toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith("?date_from=2026-01-02&changes_only=true"))).toBe(
      true,
    );
  });

  it("groups the action filter by area", async () => {
    mockFetch({
      ...base(["view_audit_log"]),
      [EVENTS]: { body: { next: null, results: [ev(1)] } },
    });
    renderRoute("/labs/lab1/audit-log");
    await screen.findByText("bob1@uni.edu");
    await userEvent.click(screen.getByLabelText("Action"));
    expect(await screen.findByText("Tasks")).toBeInTheDocument();
    expect(screen.getByText("Changed a task's status")).toBeInTheDocument();
    expect(screen.getByText("Posted a task update")).toBeInTheDocument();
  });

  it("shows changes by default and reads in one click", async () => {
    const calls = mockFetch({
      ...base(["view_audit_log"]),
      [EVENTS]: { body: { next: null, results: [ev(1)] } },
      [ALL]: {
        body: {
          next: null,
          results: [{ ...ev(2), action: "handover.generated", target_label: "Grace (Member)" }],
        },
      },
    });
    const router = renderRoute("/labs/lab1/audit-log");
    await screen.findByText("bob1@uni.edu");
    await userEvent.click(screen.getByRole("checkbox", { name: "Include views and downloads" }));
    await waitFor(() => expect(router.state.location.search).toBe("?reads=1"));
    expect(await screen.findByText("Opened a handover")).toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith("audit-events/?"))).toBe(true);
  });

  it("shows the exact time beside the relative one", async () => {
    const at = "2026-03-04T15:06:00Z";
    mockFetch({
      ...base(["view_audit_log"]),
      [EVENTS]: { body: { next: null, results: [{ ...ev(1), created_at: at }] } },
    });
    renderRoute("/labs/lab1/audit-log");
    expect(await screen.findByText(fullDate(at))).toBeInTheDocument();
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
    await openSidebarGroup("Admin");
    expect(await screen.findByRole("menuitem", { name: "Audit log" })).toBeInTheDocument();
  });
});
