import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DataIssues } from "@/pages/project/analyse/DataIssues";

const issues = [
  {
    id: "decimal",
    message: '"wert" uses a decimal comma (like "3,7"), so it is read as text, not numbers.',
    action: "Read 3,5 as 3.5",
    fix: { header: 0, skip: 0, decimal: "," as const },
  },
  {
    id: "skip",
    message: "This is a Qualtrics export, so the 2 rows under the column names were left out.",
    action: "Undo",
    fix: { header: 0, skip: 0 },
    applied: true,
  },
  { id: "dates", message: '"StartDate" looks like dates.' },
];

describe("DataIssues", () => {
  it("shows each issue with its fix, Undo for applied ones, and nothing for a clean file", async () => {
    const onFix = vi.fn();
    const { rerender, container } = render(
      <DataIssues issues={issues} busy={false} onFix={onFix} />,
    );
    expect(screen.getByRole("region", { name: "Check this file" })).toBeInTheDocument();
    expect(screen.getByText('"StartDate" looks like dates.')).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(2);
    await userEvent.click(screen.getByRole("button", { name: "Read 3,5 as 3.5" }));
    expect(onFix).toHaveBeenLastCalledWith(issues[0]!.fix);
    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(onFix).toHaveBeenLastCalledWith(issues[1]!.fix);
    rerender(<DataIssues issues={issues} busy onFix={onFix} />);
    expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
    rerender(<DataIssues issues={[]} busy={false} onFix={onFix} />);
    expect(container).toBeEmptyDOMElement();
  });
});
