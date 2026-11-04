import { useState } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CommandPalette } from "@/components/layout/CommandPalette";
import { DetailPanel } from "@/components/shared/DetailPanel";
import { EmptyState } from "@/components/shared/EmptyState";
import { FormField } from "@/components/shared/FormField";
import { Input } from "@/components/ui/input";
import { registerCommands } from "@/lib/commands";

describe("EmptyState", () => {
  it("renders its action", () => {
    render(
      <EmptyState
        title="No datasets"
        description="Add one."
        action={<button>Add dataset</button>}
      />,
    );
    expect(screen.getByRole("button", { name: "Add dataset" })).toBeInTheDocument();
  });
});

describe("FormField", () => {
  it("links label, hint and error to the input", () => {
    render(
      <FormField label="Title" hint="Keep it short" error="Title is required">
        {(p) => <Input {...p} />}
      </FormField>,
    );
    const input = screen.getByLabelText("Title");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("Title is required Keep it short");
  });
});

function Panel() {
  const [open, setOpen] = useState(true);
  return (
    <DetailPanel open={open} onOpenChange={setOpen} title="Dataset details">
      body
    </DetailPanel>
  );
}

describe("DetailPanel", () => {
  it("closes on Escape", async () => {
    render(<Panel />);
    expect(screen.getByRole("dialog", { name: "Dataset details" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("CommandPalette", () => {
  it("opens on Ctrl+K and lists registered commands", () => {
    const unregister = registerCommands([{ id: "t", label: "Test action", onSelect: () => {} }]);
    render(<CommandPalette />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    act(() => {
      fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Test action")).toBeInTheDocument();
    unregister();
  });
});
