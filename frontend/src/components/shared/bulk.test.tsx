import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DataTable } from "@/components/shared/DataTable";
import { BulkBar, runEach, useSelection } from "@/components/shared/bulk";
import { ComplianceMatrix } from "@/components/training/ComplianceMatrix";
import type { TrainingCompliance } from "@/lib/api-types";

const ROWS = ["a", "b", "c", "d"].map((id) => ({ id }));

function Demo() {
  const selection = useSelection(ROWS.map((r) => r.id));
  return (
    <>
      <BulkBar selection={selection}>
        <span>actions</span>
      </BulkBar>
      <DataTable
        columns={[{ key: "id", header: "Id", cell: (r) => r.id }]}
        rows={ROWS}
        getRowKey={(r) => r.id}
        selection={selection}
        selectLabel={(r) => `Select ${r.id}`}
      />
    </>
  );
}

describe("bulk selection", () => {
  it("selects a range with shift, all with the header box, and clears", async () => {
    const user = userEvent.setup();
    render(<Demo />);
    expect(screen.queryByText(/selected/)).toBeNull();
    await user.click(screen.getByLabelText("Select a"));
    await user.keyboard("{Shift>}");
    await user.click(screen.getByLabelText("Select c"));
    await user.keyboard("{/Shift}");
    expect(screen.getByText("3 selected")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.queryByText(/selected/)).toBeNull();
    await user.click(screen.getByLabelText("Select all rows"));
    expect(screen.getByText("4 selected")).toBeInTheDocument();
  });

  it("reports the ones that failed and carries on", async () => {
    const run = vi.fn((n: string) =>
      n === "b" ? Promise.reject(new Error("x")) : Promise.resolve(),
    );
    const r = await runEach(["a", "b", "c"], run, (n) => n);
    expect(r.done).toBe(2);
    expect(r.failed.map((f) => f.name)).toEqual(["b"]);
  });
});

const user = (id: string, name: string) => ({
  id,
  email: `${name}@example.test`,
  display_name: name,
});
const DATA = {
  requirements: [{ id: "r1", name: "WHMIS" }],
  members: [
    {
      user: user("u1", "Ann"),
      role: "member",
      cells: { r1: { status: "missing", record: null, verified: true } },
    },
    {
      user: user("u2", "Bob"),
      role: "member",
      cells: { r1: { status: "done", record: "rec", verified: false } },
    },
  ],
  summary: { done: 1, expiring: 0, expired: 0, missing: 1 },
} as unknown as TrainingCompliance;

describe("training matrix bulk actions", () => {
  it("reminds only missing cells and verifies only unverified records", async () => {
    const u = userEvent.setup();
    const remind = vi.fn(() => Promise.resolve());
    const verify = vi.fn(() => Promise.resolve());
    render(<ComplianceMatrix data={DATA} onBulkRemind={remind} onBulkVerify={verify} />);
    await u.click(screen.getByLabelText("Select all members"));
    await u.click(screen.getByRole("button", { name: "Remind about missing training" }));
    expect(remind).toHaveBeenCalledWith([{ requirement: "r1", user: "u1", label: "Ann (WHMIS)" }]);
    await u.click(screen.getByLabelText("Select all members"));
    await u.click(screen.getByRole("button", { name: "Verify selected records" }));
    expect(verify).toHaveBeenCalledWith([{ id: "rec", label: "Bob (WHMIS)" }]);
  });
});
