import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { makeLab, mockFetch, openSidebarGroup, renderRoute, SESSION, signedIn } from "@/test/utils";

const iso = (days: number) => {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};
const award = (over: Record<string, unknown>) => ({
  id: "f1",
  project_id: "p1",
  project_name: "Memory study",
  funder: "Example Fund",
  program: "Discovery",
  award_number: "A-1",
  amount: "50000.00",
  currency: "CAD",
  start_date: iso(-300),
  end_date: iso(400),
  status: "active",
  ...over,
});
const setup = (perms: string[], rows: unknown[] = []) =>
  mockFetch({
    [SESSION]: signedIn,
    "GET /api/labs/": { body: [makeLab(perms)] },
    "GET /api/labs/lab1/": { body: makeLab(perms) },
    "GET /api/labs/lab1/funding/": { body: rows },
  });

describe("Lab funding page", () => {
  it("lists every award with a link to its project, and totals per currency", async () => {
    setup(
      ["view_lab", "access_funding"],
      [
        award({}),
        award({ id: "f2", project_id: "p2", project_name: "Sleep study", end_date: iso(30) }),
        award({ id: "f3", project_name: "Pilot", amount: "1000.00", currency: "USD" }),
        award({ id: "f4", project_name: "Declined bid", status: "declined", amount: "9999.00" }),
      ],
    );
    renderRoute("/labs/lab1/funding");
    const link = await screen.findByRole("link", { name: "Sleep study" });
    expect(link).toHaveAttribute("href", "/labs/lab1/projects/p2/workflow/funding");
    expect(screen.getByText("Ends in 30 days")).toBeInTheDocument();
    const totals = screen.getByLabelText("Totals");
    expect(totals).toHaveTextContent("CA$100,000.00"); // declined awards are not counted
    expect(totals).toHaveTextContent("$1,000.00");
  });

  it("can show only awards ending within 90 days", async () => {
    setup(
      ["view_lab", "access_funding"],
      [award({}), award({ id: "f2", project_name: "Sleep study", end_date: iso(30) })],
    );
    renderRoute("/labs/lab1/funding");
    await screen.findByRole("link", { name: "Sleep study" });
    await userEvent.click(screen.getByRole("checkbox", { name: "Ends within 90 days" }));
    const rows = screen.getAllByRole("row");
    expect(within(rows[1]!).getByText("Sleep study")).toBeInTheDocument();
    expect(rows).toHaveLength(2); // the header and one award
    expect(screen.queryByRole("link", { name: "Memory study" })).toBeNull();
  });

  it("is in the sidebar for PIs, and says so (without asking the server) for everyone else", async () => {
    const calls = setup(["view_lab", "access_funding", "manage_lab", "view_audit_log"]);
    renderRoute("/labs/lab1/funding");
    await openSidebarGroup("Admin");
    expect(await screen.findByRole("menuitem", { name: "Funding" })).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/labs/lab1/funding/")).toBe(true);
  });

  it("does not ask for funding without the permission", async () => {
    const calls = setup(["view_lab", "manage_lab", "view_audit_log"]);
    renderRoute("/labs/lab1/funding");
    expect(await screen.findByText("Funding is visible to PIs only")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/labs/lab1/funding/")).toBe(false);
    await openSidebarGroup("Admin");
    expect(screen.queryByRole("menuitem", { name: "Funding" })).toBeNull();
  });
});
