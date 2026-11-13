import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { markLabel, useConfirmUnmark } from "@/components/shared/ParticipantData";

function Harness({ flagged, run }: { flagged: boolean; run: () => void }) {
  const { confirm, dialog } = useConfirmUnmark();
  return (
    <>
      <button onClick={() => confirm(flagged, "scores.csv", run)}>{markLabel(flagged)}</button>
      {dialog}
    </>
  );
}

describe("useConfirmUnmark", () => {
  it("marks in one click", async () => {
    const run = vi.fn();
    render(<Harness flagged={false} run={run} />);
    await userEvent.click(screen.getByRole("button", { name: "Mark as identifying" }));
    expect(run).toHaveBeenCalledOnce();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("asks before removing the mark", async () => {
    const run = vi.fn();
    render(<Harness flagged run={run} />);
    await userEvent.click(screen.getByRole("button", { name: "Remove identifying mark" }));
    expect(run).not.toHaveBeenCalled();
    expect(
      screen.getByText(
        "Claude and other AI tools will be able to read scores.csv again. Remove the mark?",
      ),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(run).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Remove identifying mark" }));
    await userEvent.click(screen.getByRole("button", { name: "Remove mark" }));
    expect(run).toHaveBeenCalledOnce();
  });
});
