import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

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
  spent: null,
  report_due: null,
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

  it("shows what is left and flags a report due within 30 days first", async () => {
    setup(
      ["view_lab", "access_funding"],
      [award({ spent: "20000.00", report_due: iso(10) }), award({ id: "f2", project_name: "B" })],
    );
    renderRoute("/labs/lab1/funding");
    expect(await screen.findByText("Report due in 10 days")).toBeInTheDocument();
    expect(screen.getByText("CA$30,000.00")).toBeInTheDocument();
  });

  it("lets a PI pick a project and go to its Funding step", async () => {
    mockFetch({
      [SESSION]: signedIn,
      "GET /api/labs/": { body: [makeLab(["view_lab", "access_funding"])] },
      "GET /api/labs/lab1/": { body: makeLab(["view_lab", "access_funding"]) },
      "GET /api/labs/lab1/funding/": { body: [] },
      "GET /api/labs/lab1/projects/": {
        body: [
          { id: "p1", name: "Memory study", status: "active" },
          { id: "p2", name: "Sleep study", status: "active" },
        ],
      },
    });
    renderRoute("/labs/lab1/funding");
    await userEvent.click((await screen.findAllByRole("button", { name: "Add funding" }))[0]!);
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Project" }), "p2");
    expect(screen.getByRole("link", { name: "Continue" })).toHaveAttribute(
      "href",
      "/labs/lab1/projects/p2/workflow/funding?new=1",
    );
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

    expect(await screen.findByRole("link", { name: "Funding" })).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/labs/lab1/funding/")).toBe(true);
  });

  it("does not ask for funding without the permission", async () => {
    const calls = setup(["view_lab", "manage_lab", "view_audit_log"]);
    renderRoute("/labs/lab1/funding");
    expect(await screen.findByText("Funding is visible to PIs only")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/labs/lab1/funding/")).toBe(false);

    expect(screen.queryByRole("link", { name: "Funding" })).toBeNull();
  });
});
