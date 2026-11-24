import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { Slides, slidesOf } from "@/components/documents/Slides";
import { Spreadsheet } from "@/components/documents/Spreadsheet";
import { emptySheet, type Sheet } from "@/lib/sheet";

function Harness({ start = [emptySheet()] }: { start?: Sheet[] }) {
  const [sheets, setSheets] = useState(start);
  return <Spreadsheet label="Sheet" editable sheets={sheets} onChange={setSheets} />;
}

const cell = (ref: string) => document.querySelector(`[data-cell="${ref}"]`) as HTMLElement;

describe("Spreadsheet", () => {
  it("types values, calculates formulas and shows the sum of a selection", async () => {
    const u = userEvent.setup();
    render(<Harness />);
    const grid = screen.getByRole("grid", { name: /Sheet1/ });
    await u.click(cell("A1"));
    grid.focus();
    await u.keyboard("2{Enter}");
    await u.keyboard("5{Enter}");
    await u.keyboard("=SUM(A1:A2){Enter}");
    expect(cell("A1")).toHaveTextContent("2");
    expect(cell("A3")).toHaveTextContent("7");
    // select A1:A3 with the keyboard and read the status bar
    await u.click(cell("A1"));
    await u.keyboard("{Shift>}{ArrowDown}{ArrowDown}{/Shift}");
    expect(screen.getByLabelText("Selected cell")).toHaveTextContent("A1:A3");
    expect(screen.getByText(/Sum: 14/)).toBeInTheDocument();
  });

  it("shows the formula in the formula bar, flags errors and undoes", async () => {
    const u = userEvent.setup();
    render(<Harness />);
    await u.click(cell("B1"));
    screen.getByRole("grid", { name: /Sheet1/ }).focus();
    await u.keyboard("=1/0{Enter}");
    expect(cell("B1")).toHaveTextContent("#DIV/0!");
    await u.click(cell("B1"));
    expect(screen.getByLabelText("Formula bar")).toHaveValue("=1/0");
    await u.click(screen.getByRole("button", { name: "Undo edit" }));
    expect(cell("B1")).toHaveTextContent("");
  });

  it("adds and switches sheets, and bolds the selection", async () => {
    const u = userEvent.setup();
    render(<Harness />);
    await u.click(screen.getByRole("button", { name: "Add a sheet" }));
    const tabs = screen.getByRole("tablist", { name: "Sheets" });
    expect(within(tabs).getAllByRole("tab")).toHaveLength(2);
    await u.click(within(tabs).getByRole("tab", { name: "Sheet1" }));
    await u.click(cell("A1"));
    await u.click(screen.getByRole("button", { name: "Bold" }));
    expect(screen.getByRole("button", { name: "Bold" })).toHaveAttribute("aria-pressed", "true");
  });

  it("is read-only without edit rights", () => {
    render(
      <Spreadsheet
        label="Data"
        editable={false}
        sheets={[{ name: "Data", cells: { A1: { text: "x" } } }]}
      />,
    );
    expect(cell("A1")).toHaveTextContent("x");
    expect(screen.queryByRole("toolbar", { name: "Spreadsheet tools" })).toBeNull();
  });
});

describe("Slides", () => {
  it("adds a slide and edits its title", async () => {
    const u = userEvent.setup();
    function S() {
      const [slides, set] = useState(slidesOf([]));
      return <Slides label="Deck" editable slides={slides} onChange={set} />;
    }
    render(<S />);
    await u.type(screen.getByLabelText("Slide title"), "Hello");
    await u.click(screen.getByRole("button", { name: /New slide/ }));
    expect(screen.getAllByRole("button", { name: /^Slide \d/ })).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Slide 1: Hello" })).toBeInTheDocument();
  });
});
