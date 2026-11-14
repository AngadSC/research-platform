import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ComplianceMatrix } from "@/components/training/ComplianceMatrix";
import type { TrainingCompliance } from "@/lib/api-types";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const req = (id: string, name: string, months: number | null = 12) => ({
  id,
  name,
  category: "safety" as const,
  validity_months: months,
  applies_to: "all" as const,
  roles: [],
  projects: [],
  url: "",
  notes: "",
});
const user = (id: string, name: string) => ({ id, email: `${name}@uni.edu`, display_name: name });
const cell = (status: string, extra: Record<string, unknown> = {}) => ({
  status,
  record: status === "missing" ? null : `rec-${status}`,
  completed_on: null,
  expires_on: null,
  days_left: null,
  verified: true,
  ...extra,
});

const DATA = {
  requirements: [req("r1", "WHMIS"), req("r2", "TCPS 2", null)],
  members: [
    {
      user: user("u1", "Ann"),
      role: "member",
      cells: {
        r1: cell("done", { expires_on: "2031-01-01" }),
        r2: cell("expiring", { expires_on: "2030-07-01", verified: false }),
      },
    },
    {
      user: user("u2", "Bob"),
      role: "member",
      cells: { r1: cell("expired", { expires_on: "2029-01-01" }), r2: cell("missing") },
    },
    { user: user("u3", "Cy"), role: "viewer", cells: { r1: null, r2: cell("done") } },
  ],
  summary: { done: 2, expiring: 1, expired: 1, missing: 1 },
} as unknown as TrainingCompliance;

describe("ComplianceMatrix", () => {
  it("shows every status, a dash where a training does not apply, and the summary", () => {
    render(<ComplianceMatrix data={DATA} />);
    const table = screen.getByRole("table");
    expect(within(table).getAllByText("Done")).toHaveLength(2);
    for (const s of ["Expiring", "Expired", "Missing"])
      expect(within(table).getByText(s)).toBeInTheDocument();
    expect(within(table).getByLabelText("Not required")).toBeInTheDocument();
    expect(screen.getByLabelText("Compliance summary")).toHaveTextContent(
      "2 done, 1 expiring within 60 days, 1 expired, 1 missing",
    );
    expect(within(table).getByRole("columnheader", { name: "TCPS 2" })).toBeInTheDocument();
  });

  it("offers Verify only for an unverified record, and only when allowed", async () => {
    const onVerify = vi.fn();
    const { rerender } = render(<ComplianceMatrix data={DATA} onVerify={onVerify} />);
    const buttons = screen.getAllByRole("button", { name: /^Verify/ });
    expect(buttons).toHaveLength(1);
    await userEvent.click(buttons[0]!);
    expect(onVerify).toHaveBeenCalledWith("rec-expiring");
    rerender(<ComplianceMatrix data={DATA} />);
    expect(screen.queryByRole("button", { name: /^Verify/ })).not.toBeInTheDocument();
  });

  it("says so when nothing is required", () => {
    render(<ComplianceMatrix data={{ ...DATA, requirements: [] }} />);
    expect(screen.getByText("No required trainings yet.")).toBeInTheDocument();
  });
});

const MEMBER = ["view_lab", "manage_inventory"];
const mine = {
  requirements: DATA.requirements,
  members: [DATA.members[0]],
  summary: { done: 1, expiring: 1, expired: 0, missing: 0 },
};
const record = {
  id: "rec1",
  requirement: "r1",
  requirement_name: "WHMIS",
  user: user("u1", "Ann"),
  completed_on: "2030-01-01",
  expires_on: "2031-01-01",
  notes: "",
  verified_by: null,
  verified_at: null,
  has_certificate: true,
  created_at: "2030-01-01T00:00:00Z",
};
const handlers = (extra: Record<string, unknown> = {}) =>
  ({
    [SESSION]: signedIn,
    "GET /api/labs/": { body: [makeLab(MEMBER, "member")] },
    "GET /api/labs/lab1/": { body: makeLab(MEMBER, "member") },
    "GET /api/labs/lab1/training/my/": { body: mine },
    "GET /api/labs/lab1/training/requirements/": { body: DATA.requirements },
    "GET /api/labs/lab1/training/records/": { body: [record] },
    ...extra,
  }) as Parameters<typeof mockFetch>[0];

describe("My training", () => {
  it("lists what is required with status, and the member's own records", async () => {
    mockFetch(handlers());
    renderRoute("/labs/lab1/training");
    const required = await screen.findByRole("list", { name: "Required trainings" });
    expect(within(required).getByText("WHMIS")).toBeInTheDocument();
    expect(within(required).getByText("Done")).toBeInTheDocument();
    expect(within(required).getByText("Expiring")).toBeInTheDocument();
    const records = screen.getByRole("list", { name: "My records" });
    expect(within(records).getByText(/not verified/)).toBeInTheDocument();
    expect(within(records).getByRole("link", { name: "Certificate" })).toHaveAttribute(
      "href",
      "/api/labs/lab1/training/records/rec1/certificate/",
    );
  });

  it("adds the lab-wide section for a manager only", async () => {
    const manager = makeLab(["view_lab", "manage_lab", "manage_training"]);
    const calls = mockFetch(
      handlers({
        "GET /api/labs/": { body: [manager] },
        "GET /api/labs/lab1/": { body: manager },
        "GET /api/labs/lab1/training/compliance/": { body: DATA },
        "DELETE /api/labs/lab1/training/requirements/r1/": { status: 204 },
      }),
    );
    renderRoute("/labs/lab1/training");
    const lab = await screen.findByRole("heading", { name: "Lab training" });
    // The manager's own view follows the lab section.
    const mine = screen.getByRole("heading", { name: "Log a completion" });
    expect(lab.compareDocumentPosition(mine) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // Deleting a required training asks first, and names it.
    await userEvent.click(await screen.findByRole("button", { name: "Delete WHMIS" }));
    expect(await screen.findByText("Delete WHMIS?")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Delete training" }));
    await vi.waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });

  it("is in the sidebar for a plain member and logs a completion", async () => {
    const calls = mockFetch(
      handlers({ "POST /api/labs/lab1/training/records/": { status: 201, body: record } }),
    );
    renderRoute("/labs/lab1/training");
    await screen.findByRole("list", { name: "Required trainings" });
    expect(screen.getAllByRole("link", { name: "Training" }).length).toBeGreaterThan(0);
    await userEvent.selectOptions(screen.getByLabelText("Training"), "r1");
    await userEvent.type(screen.getByLabelText("Completed on"), "2030-02-03");
    await userEvent.click(screen.getByRole("button", { name: "Save record" }));
    const post = calls.find((c) => c.method === "POST");
    expect(post?.body).toMatchObject({ requirement: "r1", completed_on: "2030-02-03" });
  });

  it("asks for a date before saving", async () => {
    mockFetch(handlers());
    renderRoute("/labs/lab1/training");
    await screen.findByRole("list", { name: "Required trainings" });
    await userEvent.selectOptions(screen.getByLabelText("Training"), "r1");
    await userEvent.click(screen.getByRole("button", { name: "Save record" }));
    expect(await screen.findByText("Enter the date")).toBeInTheDocument();
  });
});
